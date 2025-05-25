from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
import os
import logging

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# HTTP Bearer token scheme for Firebase JWT
bearer_scheme = HTTPBearer(auto_error=False)

# Check if we're in development mode
DEV_MODE = os.getenv("ENVIRONMENT", "production").lower() == "development"
if DEV_MODE:
    logger.warning("⚠️ Running in DEVELOPMENT mode - authentication required but with verbose logging")
else:
    logger.info("🔒 Running in PRODUCTION mode - strict authentication enforced")

async def auth_required(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> Dict[str, any]:
    """
    Validates the Firebase JWT token and returns user information.
    This function should be used as a dependency for all protected routes.
    Implements strict user authentication and data isolation.
    """
    logger.info("🔍 auth_required called")
    
    # Check if Firebase is properly configured
    firebase_configured = (
        os.getenv("FIREBASE_PROJECT_ID") and 
        (
            os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or
            os.getenv("FIREBASE_PRIVATE_KEY")
        )
    )
    
    logger.debug(f"🔧 Firebase configured: {firebase_configured}")
    if not firebase_configured:
        logger.error("❌ Firebase configuration missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Require credentials in all modes
    if not credentials:
        logger.error("❌ No credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Firebase token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        logger.debug("🔍 Importing Firebase admin")
        # Import here to avoid circular imports
        from app.core.firebase_admin import verify_firebase_token, get_firebase_user
        
        # Extract token from the Authorization header
        token = credentials.credentials
        if not token:
            logger.error("❌ Empty token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        logger.debug(f"🔑 Token received (length: {len(token)})")
        
        # Verify the token with revocation check in production
        check_revoked = not DEV_MODE
        if not check_revoked:
            logger.warning("⚠️ Development mode: Skipping token revocation check")
            
        decoded_token = verify_firebase_token(token, check_revoked=check_revoked)
        if not decoded_token:
            logger.error("❌ Token verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        user_id = decoded_token.get('uid')
        if not user_id:
            logger.error("❌ No user ID in decoded token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: No user ID",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Additional verification: ensure the user exists and is not disabled
        user_record = get_firebase_user(user_id)
        if not user_record:
            logger.error(f"❌ User {user_id} not found in Firebase")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found or disabled",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        # Log authentication success with email if available
        user_email = getattr(user_record, 'email', 'unknown')
        logger.info(f"✅ Authentication successful for user: {user_id} ({user_email})")
            
        # Return user info similar to suggested version
        return {
            "user_id": user_id,
            "email": user_email,
            "decoded_token": decoded_token
        }
        
    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"❌ Firebase admin not available: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        logger.error(f"❌ Authentication error: {str(e)}")
        logger.error(f"❌ Error type: {type(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def optional_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> Optional[Dict[str, any]]:
    """
    Optional authentication dependency.
    Returns user info if authenticated, None otherwise.
    """
    if not credentials:
        return None
    
    try:
        return await auth_required(credentials)
    except HTTPException:
        return None
    except Exception as e:
        logger.error(f"Optional authentication error: {str(e)}")
        return None

def resource_owner_required(resource_owner_id: str):
    """
    Factory function that creates a dependency to ensure the authenticated user
    is the owner of the resource being accessed.
    
    Args:
        resource_owner_id: The ID of the user who owns the resource
        
    Returns:
        A dependency function that validates the current user has permission to access the resource
    """
    async def validate_resource_ownership(current_user: Dict[str, any] = Depends(auth_required)) -> Dict[str, any]:
        """
        Validates that the current user is the owner of the resource.
        
        Args:
            current_user: User info from auth_required dependency
            
        Returns:
            User info if validation succeeds
            
        Raises:
            HTTPException: If the user is not the owner of the resource
        """
        from app.core.firebase_admin import validate_user_resource_access
        
        user_id = current_user["user_id"]
        if validate_user_resource_access(user_id, resource_owner_id):
            return current_user
            
        logger.warning(f"🚫 User {user_id} attempted to access resource owned by {resource_owner_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource"
        )
        
    return validate_resource_ownership
