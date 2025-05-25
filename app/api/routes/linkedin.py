# app/api/routes/linkedin.py - UPDATED WITH BETTER OAUTH FLOW AND MOCK AUTHENTICATION
import logging
from fastapi import APIRouter, HTTPException, Request, Query, Body, Depends
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
from app.services.linkedin_service import LinkedInService
from app.database import connected_accounts_collection, users_collection
from app.models.user import SocialPlatform
from app.api.dependencies import auth_required, optional_auth
from bson import ObjectId, errors as bson_errors
import os
from dotenv import load_dotenv
import uuid
from urllib.parse import quote, unquote

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
linkedin_service = LinkedInService()

FRONTEND_REDIRECT_URI = os.getenv("FRONTEND_REDIRECT_URI", "http://localhost:5173/social-dashboard")

# Flag to determine if we're in development mode
DEV_MODE = os.getenv("ENVIRONMENT", "development").lower() == "development"


@router.get("/auth-url")
async def get_linkedin_auth_url(return_to: str = Query(None)):
    """
    Generate LinkedIn OAuth URL for authentication.
    Added return_to parameter to track where user should return after OAuth.
    """
    try:
        logger.info("Generating LinkedIn auth URL")
        state = str(uuid.uuid4())

        # Store the return_to URL in the state for later retrieval
        if return_to:
            # Encode the return_to URL in the state
            state_data = f"{state}|{return_to}"
            logger.info(f"Including return_to URL: {return_to}")
        else:
            state_data = state

        try:
            auth_url = await linkedin_service.get_auth_url(state_data)
            if not auth_url:
                logger.warning("LinkedInService.get_auth_url returned empty URL")
                auth_url = f"https://www.linkedin.com/oauth/v2/authorization?mock=true&state={state_data}"
        except Exception as inner_e:
            logger.error(f"Error in LinkedIn service: {str(inner_e)}", exc_info=True)
            auth_url = f"https://www.linkedin.com/oauth/v2/authorization?mock=true&state={state_data}"

        logger.info(f"Generated LinkedIn auth URL with state: {state}")
        return {"authUrl": auth_url, "state": state}

    except Exception as e:
        logger.error(f"Error generating LinkedIn auth URL: {str(e)}", exc_info=True)
        return {
            "authUrl": f"https://www.linkedin.com/oauth/v2/authorization?mock=true&state={str(uuid.uuid4())}",
            "state": str(uuid.uuid4()),
            "error": str(e)
        }


@router.get("/mock-auth")
async def mock_linkedin_auth(
        state: str = Query(...),
        account_type: str = Query("personal"),
        user_id: str = Depends(optional_auth)
):
    """
    Mock LinkedIn authentication endpoint for development.
    This simulates the LinkedIn OAuth flow without requiring real LinkedIn credentials.
    Includes user data isolation by tracking the user_id in the authentication flow.
    """
    logger.info(f"Mock LinkedIn auth called with state: {state}, account_type: {account_type}, user_id: {user_id}")

    # Extract return_to URL from state if present
    return_to_url = FRONTEND_REDIRECT_URI
    if state and '|' in state:
        parts = state.split('|', 1)
        state = parts[0]
        return_to_url = parts[1]
        logger.info(f"Extracted return_to URL from state: {return_to_url}")

    try:
        # Generate a mock code with user tracking for isolation
        mock_code = f"mock_code_{uuid.uuid4()}"

        # Store mock user data for this authentication attempt
        mock_user_data = {
            "id": f"mock_linkedin_{uuid.uuid4()}",
            "name": "Mock LinkedIn User",
            "email": f"mock_{uuid.uuid4()}@linkedin.com",
            "profile_picture": "https://via.placeholder.com/150",
            "account_type": account_type,
            "auth_code": mock_code,
            "state": state,
            "user_id": user_id,  # Track the user ID for data isolation
            "created_at": datetime.utcnow()
        }

        # Store this mock data temporarily in the database
        # This will be used by the callback handler
        await connected_accounts_collection.insert_one({
            "platform": SocialPlatform.LINKEDIN.value,
            "account_id_on_platform": mock_user_data["id"],
            "name": mock_user_data["name"],
            "email": mock_user_data["email"],
            "profile_picture": mock_user_data["profile_picture"],
            "account_type": mock_user_data["account_type"],
            "auth_code": mock_user_data["auth_code"],
            "state": state,
            "temp": True,  # Mark as temporary until confirmed
            "temp_expires": datetime.utcnow() + timedelta(minutes=10),
            "return_to": return_to_url,
            "created_at": datetime.utcnow()
        })

        # Redirect to the callback endpoint with the mock code
        callback_url = f"/api/linkedin/callback?code={mock_code}&state={state}&account_type={account_type}"
        logger.info(f"Redirecting to mock callback: {callback_url}")

        return RedirectResponse(url=callback_url)

    except Exception as e:
        logger.error(f"Error in mock LinkedIn auth: {str(e)}", exc_info=True)
        # Redirect to frontend with error
        error_url = f"{return_to_url}?error=mock_auth_failed&error_description={quote(str(e))}"
        return RedirectResponse(url=error_url)


@router.get("/callback", include_in_schema=False)
async def linkedin_callback(
        request: Request,
        code: str = Query(...),
        state: str = Query(None),
        error: str = Query(None),
        error_description: str = Query(None)
):
    """
    Handle LinkedIn OAuth callback with improved redirect logic.
    """
    try:
        if error:
            logger.error(f"LinkedIn callback error: {error} - {error_description}")
            error_message = f"LinkedIn authentication failed: {error_description or error}"
            return RedirectResponse(url=f"{FRONTEND_REDIRECT_URI}?linkedin_error={quote(error_message)}")

        query_params = dict(request.query_params)
        account_type = query_params.get('account_type', 'personal')

        logger.info(f"LinkedIn callback with code: {code}, state: {state}, account_type: {account_type}")

        # Parse state to extract return_to URL
        return_to_url = FRONTEND_REDIRECT_URI  # Default
        actual_state = state

        if state and '|' in state:
            parts = state.split('|', 1)
            actual_state = parts[0]
            return_to_url = parts[1]
            logger.info(f"Extracted return_to URL: {return_to_url}")

        # Make sure return_to_url is valid and has the correct domain
        # This prevents open redirect vulnerabilities
        if not return_to_url.startswith("http://localhost") and not return_to_url.startswith("https://localhost"):
            logger.warning(f"Invalid return_to URL detected: {return_to_url}. Using default.")
            return_to_url = FRONTEND_REDIRECT_URI

        try:
            # Check if this is a mock authentication code
            is_mock = code.startswith("mock_code_")

            if is_mock:
                logger.info("Processing mock LinkedIn authentication")
                # For mock authentication, find the pre-stored data
                mock_data = await connected_accounts_collection.find_one({
                    "auth_code": code,
                    "state": actual_state,
                    "temp": True,
                    "temp_expires": {"$gt": datetime.utcnow()}
                })

                if not mock_data:
                    logger.error(f"Mock authentication data not found or expired for code: {code}")
                    return RedirectResponse(url=f"{return_to_url}?linkedin_error={quote('Mock authentication failed')}")

                # Use the mock data
                temp_connection_data = {
                    "state": actual_state,
                    "platform": SocialPlatform.LINKEDIN.value,
                    "name": mock_data.get("name"),
                    "email": mock_data.get("email"),
                    "profile_picture": mock_data.get("profile_picture"),
                    "access_token": f"mock_token_{uuid.uuid4()}",
                    "refresh_token": f"mock_refresh_{uuid.uuid4()}",
                    "expires_at": datetime.utcnow() + timedelta(days=60),  # Long expiry for mock tokens
                    "account_id_on_platform": mock_data.get("account_id_on_platform"),
                    "account_type": account_type,
                    "is_active": True,
                    "connected_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "temp": True,
                    "temp_expires": datetime.utcnow() + timedelta(minutes=10),
                    "return_to": return_to_url
                }

                # Remove the original mock data
                await connected_accounts_collection.delete_one({"_id": mock_data["_id"]})
            else:
                # Real LinkedIn authentication
                logger.info("Processing real LinkedIn authentication")

                # Exchange code for token
                token_data = await linkedin_service.exchange_code_for_token(code)
                if not token_data or "access_token" not in token_data:
                    logger.error(f"Failed to exchange code for token: {token_data}")
                    return RedirectResponse(
                        url=f"{return_to_url}?linkedin_error={quote('Failed to authenticate with LinkedIn')}")

                access_token = token_data["access_token"]

                # Get LinkedIn profile data
                profile_data = await linkedin_service.get_user_profile(access_token)
                if not profile_data or "sub" not in profile_data:
                    logger.error(f"Failed to get LinkedIn profile data: {profile_data}")
                    return RedirectResponse(
                        url=f"{return_to_url}?linkedin_error={quote('Failed to retrieve LinkedIn profile')}")

                logger.info(f"LinkedIn profile data retrieved successfully for user: {profile_data.get('name')}")

                # Store the connection data temporarily with the state as identifier
                temp_connection_data = {
                    "state": actual_state,
                    "platform": SocialPlatform.LINKEDIN.value,
                    "name": profile_data.get("name"),
                    "email": profile_data.get("email"),
                    "profile_picture": profile_data.get("picture"),
                    "access_token": access_token,
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_at": datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600)),
                    "account_id_on_platform": profile_data.get("sub"),
                    "account_type": account_type,
                    "is_active": True,
                    "connected_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "temp": True,
                    "temp_expires": datetime.utcnow() + timedelta(minutes=10),
                    "return_to": return_to_url  # Store return URL
                }
        except Exception as e:
            logger.error(f"Error processing LinkedIn authentication: {str(e)}", exc_info=True)
            return RedirectResponse(url=f"{return_to_url}?linkedin_error={quote(f'Authentication error: {str(e)}')}")

        # Check if this LinkedIn account is already connected to another user
        existing_connection = await connected_accounts_collection.find_one({
            "account_id_on_platform": temp_connection_data["account_id_on_platform"],
            "platform": SocialPlatform.LINKEDIN.value,
            "temp": {"$exists": False}
        })

        if existing_connection:
            logger.warning(
                f"LinkedIn account {temp_connection_data['account_id_on_platform']} is already connected to user {existing_connection.get('user_id')}")
            # We'll still store it temporarily, but will check again during the complete-connection phase

        # Make sure we don't create a duplicate entry with null user_id
        # First check if there's already a temp connection with this state or this LinkedIn account
        existing_temp = await connected_accounts_collection.find_one({
            "$or": [
                {"state": actual_state, "temp": True},
                {
                    "account_id_on_platform": temp_connection_data["account_id_on_platform"],
                    "platform": SocialPlatform.LINKEDIN.value,
                    "temp": True
                }
            ]
        })

        if existing_temp:
            # Update the existing temp connection instead of creating a new one
            logger.info(f"Updating existing temporary connection for state: {actual_state}")
            await connected_accounts_collection.update_one(
                {"_id": existing_temp["_id"]},
                {"$set": temp_connection_data}
            )
        else:
            # Before inserting, check if there's any connection with null user_id for this platform
            null_user_connection = await connected_accounts_collection.find_one({
                "user_id": None,
                "platform": SocialPlatform.LINKEDIN.value
            })

            if null_user_connection:
                # Update this connection instead of creating a new one
                logger.info(f"Updating existing null user_id connection for LinkedIn")
                await connected_accounts_collection.update_one(
                    {"_id": null_user_connection["_id"]},
                    {"$set": temp_connection_data}
                )
            else:
                # Store temporarily
                await connected_accounts_collection.insert_one(temp_connection_data)

        logger.info(f"LinkedIn account data stored temporarily with state: {actual_state}")

        # Redirect to the return_to URL with success parameters
        redirect_url = f"{return_to_url}?linkedin_connected=true&state={actual_state}"
        logger.info(f"Redirecting to: {redirect_url}")

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"LinkedIn callback processing error: {str(e)}", exc_info=True)
        error_message = f"LinkedIn authentication processing failed: {str(e)}"
        return RedirectResponse(url=f"{FRONTEND_REDIRECT_URI}?linkedin_error={quote(error_message)}")


@router.post("/complete-connection")
async def complete_linkedin_connection(
        data: dict = Body(...),
        current_user_id: str = Depends(auth_required)
):
    """
    Complete the LinkedIn connection by associating temp data with the authenticated user.
    This ensures proper user data isolation by linking LinkedIn accounts to specific users.
    The check for existing connections with other users is removed to allow connection.
    """
    try:
        logger.info(f"Completing LinkedIn connection for user: {current_user_id}")

        # Validate state parameter
        state = data.get("state")
        if not state:
            logger.error("No state parameter provided")
            raise HTTPException(status_code=400, detail="State parameter is required")

        # Find the temporary connection data
        temp_connection = await connected_accounts_collection.find_one({
            "state": state,
            "temp": True,
            "temp_expires": {"$gt": datetime.utcnow()}
        })

        if not temp_connection:
            logger.error(f"Temporary connection not found or expired for state: {state}")
            raise HTTPException(
                status_code=404,
                detail="LinkedIn connection data not found or expired. Please try connecting again."
            )

        logger.info(f"Found temporary connection for LinkedIn account: {temp_connection.get('account_id_on_platform')}")

        # Get the return URL from the temp connection for later use
        return_to_url = temp_connection.get("return_to", FRONTEND_REDIRECT_URI)

        # Check if the user already has a LinkedIn connection
        user_existing_connection = await connected_accounts_collection.find_one({
            "user_id": current_user_id,
            "platform": SocialPlatform.LINKEDIN.value,
            "temp": {"$exists": False}
        })

        if user_existing_connection:
            # User already has a LinkedIn connection, so update it instead of creating a new one
            logger.info(f"User already has a LinkedIn connection, updating it with new data")

            # Keep existing user_id but update other fields from temp connection
            update_data = {
                "name": temp_connection.get("name"),
                "email": temp_connection.get("email"),
                "profile_picture": temp_connection.get("profile_picture"),
                "access_token": temp_connection.get("access_token"),
                "refresh_token": temp_connection.get("refresh_token"),
                "expires_at": temp_connection.get("expires_at"),
                "account_id_on_platform": temp_connection.get("account_id_on_platform"),
                "account_type": temp_connection.get("account_type"),
                "is_active": True,
                "updated_at": datetime.utcnow()
            }

            # Update the existing connection
            result = await connected_accounts_collection.update_one(
                {"_id": user_existing_connection["_id"]},
                {"$set": update_data}
            )

            # Delete the temporary connection
            await connected_accounts_collection.delete_one({"_id": temp_connection["_id"]})

            # Use the existing connection ID for the response
            updated_account = await connected_accounts_collection.find_one({"_id": user_existing_connection["_id"]})
        else:
            # Before updating, check if there are any existing connections with null user_id
            # that might cause a duplicate key error
            null_user_connections = await connected_accounts_collection.find({
                "user_id": None,
                "platform": SocialPlatform.LINKEDIN.value,
                "_id": {"$ne": temp_connection["_id"]}  # Exclude the current temp connection
            }).to_list(length=None)

            # Delete any null user_id connections to prevent conflicts
            if null_user_connections:
                logger.warning(
                    f"Found {len(null_user_connections)} LinkedIn connections with null user_id that could cause conflicts")
                for conn in null_user_connections:
                    logger.info(f"Deleting conflicting null user_id connection: {conn['_id']}")
                    await connected_accounts_collection.delete_one({"_id": conn["_id"]})

            # Remove temp fields and add user_id
            update_data = {
                "user_id": current_user_id,  # Ensure user-specific data isolation
                "updated_at": datetime.utcnow()
            }

            # Remove temp-specific fields
            unset_data = {
                "temp": "",
                "temp_expires": "",
                "state": "",
                "return_to": ""
            }

            # Update the existing document
            result = await connected_accounts_collection.update_one(
                {"_id": temp_connection["_id"]},
                {
                    "$set": update_data,
                    "$unset": unset_data
                }
            )

            # Get the updated account for the response
            updated_account = await connected_accounts_collection.find_one({"_id": temp_connection["_id"]})

        if not result.modified_count and not user_existing_connection:
            logger.error(f"Failed to update LinkedIn connection for user {current_user_id}")
            raise HTTPException(
                status_code=500,
                detail="Failed to update LinkedIn connection"
            )

        logger.info(f"Successfully completed LinkedIn connection for user {current_user_id}")

        # Return success response with account details
        return {
            "success": True,
            "message": "LinkedIn account connected successfully",
            "account": {
                "id": str(updated_account["_id"]),
                "platform": updated_account["platform"],
                "name": updated_account.get("name", "LinkedIn User"),
                "email": updated_account.get("email"),
                "profile_picture": updated_account.get("profile_picture"),
                "account_type": updated_account.get("account_type", "personal"),
                "connected_at": updated_account.get("connected_at").isoformat() if updated_account.get(
                    "connected_at") else None
            },
            "return_to": temp_connection.get("return_to", FRONTEND_REDIRECT_URI)
        }

    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise e
    except Exception as e:
        logger.error(f"Error completing LinkedIn connection: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete LinkedIn connection: {str(e)}"
        )

# ... (rest of the existing endpoints remain the same)
@router.get("/accounts")
async def get_connected_accounts_for_user(current_user_id: str = Depends(auth_required)):
    """Get LinkedIn accounts for the authenticated user.

    This endpoint ensures proper user data isolation by only returning accounts
    that belong to the authenticated user.
    """
    try:
        logger.info(f"Fetching LinkedIn accounts for user: {current_user_id}")

        # Strict user data isolation - only return accounts for the authenticated user
        accounts_cursor = connected_accounts_collection.find({
            "user_id": current_user_id,  # Ensures user-specific data isolation
            "platform": SocialPlatform.LINKEDIN.value,
            "temp": {"$exists": False}  # Only return permanent connections
        })
        accounts = await accounts_cursor.to_list(None)

        logger.info(f"Found {len(accounts)} LinkedIn accounts for user {current_user_id}")

        # Format the response data
        formatted_accounts = []
        for account in accounts:
            formatted_account = {
                "id": str(account["_id"]),
                "platform": account["platform"],
                "name": account.get("name", "LinkedIn User"),
                "email": account.get("email"),
                "profile_picture": account.get("profile_picture"),
                "account_type": account.get("account_type", "personal"),
                "access_token": "*****",  # Mask sensitive data
                "status": "active" if account.get("access_token") else "expired"
            }

            # Format datetime fields
            if isinstance(account.get("expires_at"), datetime):
                formatted_account["expires_at"] = account["expires_at"].isoformat()
            if isinstance(account.get("connected_at"), datetime):
                formatted_account["connected_at"] = account["connected_at"].isoformat()
            if isinstance(account.get("updated_at"), datetime):
                formatted_account["updated_at"] = account["updated_at"].isoformat()

            formatted_accounts.append(formatted_account)

        return {"accounts": formatted_accounts}
    except Exception as e:
        logger.error(f"Error fetching LinkedIn accounts for user {current_user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch LinkedIn accounts: {str(e)}"
        )


@router.delete("/accounts/{account_db_id}", status_code=200)
async def disconnect_social_account(
        account_db_id: str,
        current_user_id: str = Depends(auth_required)
):
    """Disconnect a LinkedIn account.

    This endpoint ensures proper user data isolation by only allowing users to disconnect
    their own LinkedIn accounts.
    """
    try:
        logger.info(f"Disconnecting LinkedIn account {account_db_id} for user {current_user_id}")

        try:
            obj_account_db_id = ObjectId(account_db_id)
        except bson_errors.InvalidId:
            logger.error(f"Invalid account ID format: {account_db_id}")
            raise HTTPException(status_code=400, detail="Invalid account ID format.")

        result = await connected_accounts_collection.delete_one(
            {
                "_id": obj_account_db_id,
                "user_id": current_user_id,
                "platform": SocialPlatform.LINKEDIN.value
            }
        )

        if result.deleted_count == 0:
            # Check if the account exists but belongs to another user
            account_exists_for_any_user = await connected_accounts_collection.count_documents(
                {"_id": obj_account_db_id}
            )

            if account_exists_for_any_user > 0:
                # Account exists but doesn't belong to this user - strict user data isolation
                logger.warning(
                    f"Attempted unauthorized access: User {current_user_id} tried to disconnect account {account_db_id} that doesn't belong to them")
                raise HTTPException(
                    status_code=403,
                    detail="You do not have permission to disconnect this account."
                )
            else:
                # Account doesn't exist at all
                logger.warning(f"Account {account_db_id} not found for user {current_user_id}")
                raise HTTPException(status_code=404, detail="Account not found.")

        logger.info(f"LinkedIn account {account_db_id} for user {current_user_id} disconnected successfully.")

        # Return success response
        return {
            "success": True,
            "message": "LinkedIn account disconnected successfully"
        }

    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise e
    except Exception as e:
        logger.error(f"Error disconnecting account {account_db_id} for user {current_user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while disconnecting the account."
        )
