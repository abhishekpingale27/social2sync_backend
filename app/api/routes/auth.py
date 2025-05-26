# Backend/app/api/routes/auth.py - FIXED VERSION
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.user import UserCreate, UserLogin, UserViewModel, PasswordResetRequest, PasswordReset, FirebaseAuth, UserProfile
from app.services.auth_service import (
    create_new_user, verify_user_credentials, request_password_reset, reset_password,
    get_or_create_user_by_firebase_uid, get_user_by_firebase_uid, update_user_profile
)
from app.database import users_collection
from app.api.dependencies import auth_required
from app.core.firebase_admin import verify_firebase_token
from bson import ObjectId
from datetime import datetime
from typing import Dict, Any
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Import Firebase admin correctly
try:
    from firebase_admin import auth as firebase_auth
    FIREBASE_AVAILABLE = True
    logger.info("✅ Firebase admin auth imported successfully")
except ImportError as e:
    logger.error(f"❌ Firebase admin import failed: {e}")
    FIREBASE_AVAILABLE = False

router = APIRouter()

@router.post("/register", response_model=UserViewModel, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate):
    try:
        created_user_dict = await create_new_user(user_in)
        return UserViewModel(**created_user_dict)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration."
        )

@router.post("/login")
async def login_user(form_data: UserLogin):
    user_dict_from_db = await verify_user_credentials(email=form_data.email, password=form_data.password)
    if not user_dict_from_db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    current_time = datetime.utcnow()
    try:
        await users_collection.update_one(
            {"_id": ObjectId(user_dict_from_db["id"])},
            {"$set": {"last_login": current_time}}
        )
        user_dict_from_db["last_login"] = current_time
    except Exception as e:
        logger.error(f"Error updating last_login: {e}")
    try:
        user_view = UserViewModel(**user_dict_from_db)
    except Exception as pydantic_error:
        logger.error(f"Pydantic validation error during login: {pydantic_error}")
        logger.error(f"Data passed to UserViewModel: {user_dict_from_db}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error: Could not process user data."
        )
    return {
        "message": "Login successful!",
        "user": user_view
    }

@router.post("/forgot-password")
async def forgot_password(reset_request: PasswordResetRequest):
    try:
        result = await request_password_reset(reset_request)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error processing password reset request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/reset-password")
async def reset_password_endpoint(reset_data: PasswordReset):
    try:
        result = await reset_password(reset_data)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error resetting password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/firebase-auth")
async def firebase_auth_endpoint(auth_data: FirebaseAuth):
    """
    Authenticate with Firebase token and get or create user in our database.
    
    Args:
        auth_data: Firebase authentication data with token
        
    Returns:
        User data and message
    """
    try:
        logger.info("🔄 Processing Firebase auth request...")
        
        if not auth_data or not auth_data.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token is required"
            )
            
        logger.info("🔑 Verifying Firebase token...")
        # Verify the Firebase token - this should return just the UID string
        uid = verify_firebase_token(auth_data.token)
        if not uid:
            logger.error("❌ Token verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Firebase token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Ensure UID is a string (critical fix)
        if not isinstance(uid, str):
            logger.error(f"❌ Invalid UID type from verify_firebase_token: {type(uid)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication token format error"
            )
        
        logger.info(f"✅ Token verified for user: {uid}")
        
        # Check if Firebase admin is available
        if not FIREBASE_AVAILABLE:
            logger.warning("⚠️ Firebase admin not available, using basic auth")
            # Fallback: create user with basic info
            user_dict = await get_or_create_user_by_firebase_uid(
                uid=uid,
                email="user@example.com",  # We'll update this when we get proper user info
                display_name="Firebase User"
            )
            
            return {
                "message": "Firebase authentication successful (limited info)",
                "user": user_dict
            }
        
        try:
            logger.info(f"🔍 Getting Firebase user info for: {uid}")
            # Import the helper function
            from app.core.firebase_admin import get_firebase_user
            
            # Get Firebase user info using the helper function
            firebase_user = get_firebase_user(uid)
            if not firebase_user:
                raise Exception("Could not retrieve Firebase user info")
                
            logger.info(f"✅ Firebase user info retrieved: {firebase_user.email}")
            
            # Get or create user in our database with the UID string
            user_dict = await get_or_create_user_by_firebase_uid(
                uid=uid,  # This is now guaranteed to be a string
                email=firebase_user.email,
                display_name=firebase_user.display_name
            )
            
            logger.info("✅ User processed successfully")
            
            # Return user data
            return {
                "message": "Firebase authentication successful",
                "user": user_dict
            }
            
        except Exception as firebase_error:
            logger.error(f"❌ Firebase user retrieval error: {firebase_error}")
            logger.error(f"Error type: {type(firebase_error)}")
            
            # Fallback: create user with UID and basic email
            try:
                # Try to extract email from the token if possible
                user_dict = await get_or_create_user_by_firebase_uid(
                    uid=uid,  # This is guaranteed to be a string
                    email=f"{uid}@firebase.user",  # Temporary email
                    display_name="Firebase User"
                )
                
                return {
                    "message": "Firebase authentication successful (fallback)",
                    "user": user_dict
                }
            except Exception as fallback_error:
                logger.error(f"❌ Fallback user creation failed: {fallback_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user account"
                )
            
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Error during Firebase authentication: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Return a more generic error message to avoid exposing sensitive information
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed. Please try again later."
        )

@router.get("/me")
async def get_current_user(current_user_id: str = Depends(auth_required)):
    """
    Get the current authenticated user's profile.
    
    Args:
        current_user_id: The authenticated user ID (from token)
        
    Returns:
        User profile data
    """
    try:
        user = await get_user_by_firebase_uid(current_user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.put("/me")
async def update_current_user(profile_data: UserProfile, current_user_id: str = Depends(auth_required)):
    """
    Update the current authenticated user's profile.
    
    Args:
        profile_data: Profile data to update
        current_user_id: The authenticated user ID (from token)
        
    Returns:
        Updated user profile
    """
    try:
        updated_user = await update_user_profile(current_user_id, profile_data.dict(exclude_unset=True))
        return {
            "message": "Profile updated successfully",
            "user": updated_user
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )
