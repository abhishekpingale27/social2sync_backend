import os
import json
from typing import Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, auth
    FIREBASE_AVAILABLE = True
    logger.info("✅ Firebase Admin SDK imported successfully")
except ImportError as e:
    logger.warning(f"❌ Firebase Admin SDK not available: {e}")
    logger.warning("Please install firebase-admin: pip install firebase-admin")
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    auth = None

def initialize_firebase() -> bool:
    """
    Initialize Firebase Admin SDK.
    Returns True if successful, False otherwise.
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firebase Admin SDK not available")
        return False
    
    if len(firebase_admin._apps) > 0:
        logger.info("✅ Firebase already initialized")
        return True
    
    try:
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        
        if not project_id or not service_account_json:
            logger.error("❌ Missing FIREBASE_PROJECT_ID or FIREBASE_SERVICE_ACCOUNT_JSON")
            return False
        
        logger.info("🔑 Using service account JSON")
        cred_dict = json.loads(service_account_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {'projectId': project_id})
        logger.info("✅ Firebase initialized")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Firebase initialization failed: {e}")
        return False

def verify_firebase_token(token: str, check_revoked: bool = True) -> Optional[str]:
    """
    Verify Firebase ID token and return the user ID.
    Args:
        token: Firebase ID token
        check_revoked: Check if token is revoked
    Returns:
        User ID if valid, None otherwise
    """
    DEV_MODE = os.getenv("ENVIRONMENT", "production").lower() == "development"
    
    if not FIREBASE_AVAILABLE or not initialize_firebase():
        logger.error("❌ Firebase not available or not initialized")
        if DEV_MODE:
            logger.warning("⚠️ Development mode: Returning test UID")
            return "test_user_firebase_uid_12345"
        return None
    
    try:
        decoded_token = auth.verify_id_token(token, check_revoked=not DEV_MODE)
        user_id = decoded_token.get('uid')
        if not user_id:
            logger.error("❌ No user ID in token")
            return None
            
        logger.info(f"✅ Token verified for user: {user_id}")
        return user_id
            
    except auth.ExpiredIdTokenError:
        logger.error("❌ Token expired")
        return None
    except auth.RevokedIdTokenError:
        logger.error("❌ Token revoked")
        return None
    except auth.InvalidIdTokenError:
        logger.error("❌ Invalid token")
        return None
    except Exception as e:
        logger.error(f"❌ Token verification failed: {e}")
        return None

def get_firebase_user(uid: str) -> Optional[object]:
    """
    Get Firebase user by UID.
    Args:
        uid: Firebase user ID (string)
    Returns:
        User record if found, None otherwise
    """
    if not FIREBASE_AVAILABLE or not initialize_firebase():
        logger.error("❌ Firebase not available or not initialized")
        return None
    
    if not isinstance(uid, str):
        logger.error(f"❌ Invalid UID type: {type(uid)}, expected string")
        return None
    
    try:
        user_record = auth.get_user(uid)
        logger.info(f"✅ User retrieved: {user_record.email}")
        return user_record
    except auth.UserNotFoundError:
        logger.error(f"❌ User not found: {uid}")
        return None
    except Exception as e:
        logger.error(f"❌ Failed to get user {uid}: {e}")
        return None

def validate_user_resource_access(user_id: str, resource_owner_id: str) -> bool:
    """
    Validate user permission to access a resource.
    """
    if not user_id or not resource_owner_id:
        logger.error("❌ Missing user_id or resource_owner_id")
        return False
        
    if user_id == resource_owner_id:
        logger.info(f"✅ User {user_id} has permission")
        return True
        
    logger.warning(f"⚠️ User {user_id} attempted to access resource owned by {resource_owner_id}")
    return False

# Initialize Firebase
logger.info("🚀 Initializing Firebase...")
firebase_initialized = initialize_firebase()
if firebase_initialized:
    logger.info("✅ Firebase initialized successfully")
else:
    logger.error("❌ Firebase initialization failed")
