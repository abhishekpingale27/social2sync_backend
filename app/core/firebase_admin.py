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
    logger.warning("Please install firebase-admin package: pip install firebase-admin")
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    auth = None

def initialize_firebase() -> bool:
    """
    Initialize Firebase Admin SDK with proper error handling.
    Returns True if successful, False otherwise.
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firebase Admin SDK not available")
        return False
    
    # Check if already initialized
    if len(firebase_admin._apps) > 0:
        logger.info("✅ Firebase already initialized")
        return True
    
    try:
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if not project_id:
            logger.error("❌ FIREBASE_PROJECT_ID not found in environment variables")
            return False
        
        # Prefer service account JSON from environment variable (production)
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            logger.info("🔑 Using service account JSON from environment variable")
            try:
                cred_dict = json.loads(service_account_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {'projectId': project_id})
                logger.info("✅ Firebase initialized with service account JSON")
                return True
            except json.JSONDecodeError as e:
                logger.error(f"❌ Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
                return False
            except Exception as e:
                logger.error(f"❌ Error initializing with service account JSON: {e}")
                return False
        
        # Fallback to individual environment variables (alternative)
        private_key = os.getenv("FIREBASE_PRIVATE_KEY")
        client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
        
        if private_key and client_email:
            logger.info("🔑 Using individual Firebase environment variables")
            private_key = private_key.replace('\\n', '\n')
            service_account_info = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": private_key,
                "client_email": client_email,
                "client_id": os.getenv("FIREBASE_CLIENT_ID", ""),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email}"
            }
            try:
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred, {'projectId': project_id})
                logger.info("✅ Firebase initialized with individual environment variables")
                return True
            except Exception as e:
                logger.error(f"❌ Error initializing with individual environment variables: {e}")
                return False
        
        # Try Application Default Credentials (for production environments like Render)
        logger.info("🔑 Trying Application Default Credentials")
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {'projectId': project_id})
            logger.info("✅ Firebase initialized with Application Default Credentials")
            return True
        except Exception as adc_error:
            logger.error(f"❌ Failed to initialize with Application Default Credentials: {adc_error}")
            return False
        
        logger.error("❌ All Firebase initialization methods failed")
        return False
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Firebase: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        return False

def verify_firebase_token(token: str, check_revoked: bool = True) -> Optional[dict]:
    """
    Verify Firebase ID token and return the decoded token.
    
    Args:
        token: The Firebase ID token to verify
        check_revoked: Whether to check if the token has been revoked
        
    Returns:
        Decoded token if valid, None otherwise
    """
    DEV_MODE = os.getenv("ENVIRONMENT", "production").lower() == "development"
    
    if not FIREBASE_AVAILABLE:
        logger.warning("⚠️ Firebase not available, cannot verify token")
        if DEV_MODE:
            logger.warning("⚠️ Development mode: Returning test token")
            return {"uid": "test_user_firebase_uid_12345"}
        return None
    
    if not initialize_firebase():
        logger.error("❌ Firebase not initialized, cannot verify token")
        if DEV_MODE:
            logger.warning("⚠️ Development mode: Returning test token")
            return {"uid": "test_user_firebase_uid_12345"}
        return None
    
    try:
        if DEV_MODE:
            logger.info("⚠️ Running in development mode, lenient token verification")
            decoded_token = auth.verify_id_token(token, check_revoked=False)
        else:
            decoded_token = auth.verify_id_token(token, check_revoked=check_revoked)
        
        user_id = decoded_token.get('uid')
        if not user_id:
            logger.error("❌ No user ID found in token")
            return None
            
        logger.info(f"✅ Token verified successfully for user: {user_id}")
        return decoded_token
            
    except auth.ExpiredIdTokenError:
        logger.error("❌ Token has expired")
        return None
    except auth.RevokedIdTokenError:
        logger.error("❌ Token has been revoked")
        return None
    except auth.InvalidIdTokenError:
        logger.error("❌ Token is invalid")
        return None
    except Exception as e:
        logger.error(f"❌ Token verification failed: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        return None

def get_firebase_user(uid: str):
    """
    Get Firebase user information by UID.
    
    Args:
        uid: The Firebase user ID (string)
        
    Returns:
        Firebase user record if found, None otherwise
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("⚠️ Firebase not available, cannot get user")
        return None
    
    if not initialize_firebase():
        logger.error("❌ Firebase not initialized, cannot get user")
        return None
    
    if not isinstance(uid, str):
        logger.error(f"❌ Invalid UID type: {type(uid)}, expected string")
        return None
    
    try:
        user_record = auth.get_user(uid)
        logger.info(f"✅ Firebase user retrieved: {user_record.email}")
        return user_record
    except auth.UserNotFoundError:
        logger.error(f"❌ Firebase user not found: {uid}")
        return None
    except Exception as e:
        logger.error(f"❌ Failed to get Firebase user {uid}: {str(e)}")
        return None

def validate_user_resource_access(user_id: str, resource_owner_id: str) -> bool:
    """
    Validate that a user has permission to access a resource.
    
    Args:
        user_id: The ID of the user making the request
        resource_owner_id: The ID of the user who owns the resource
        
    Returns:
        True if the user has permission, False otherwise
    """
    if not user_id or not resource_owner_id:
        logger.error(f"❌ Missing user_id or resource_owner_id in permission check")
        return False
        
    if user_id == resource_owner_id:
        logger.info(f"✅ User {user_id} has permission to access resource owned by {resource_owner_id}")
        return True
        
    logger.warning(f"⚠️ User {user_id} attempted to access resource owned by {resource_owner_id}")
    return False

def create_firebase_user(email: str, password: str, display_name: str = None):
    """
    Create a new Firebase user.
    
    Args:
        email: User email
        password: User password
        display_name: Optional display name
        
    Returns:
        Firebase user record if created successfully, None otherwise
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("⚠️ Firebase not available, cannot create user")
        return None
    
    if not initialize_firebase():
        logger.error("❌ Firebase not initialized, cannot create user")
        return None
    
    try:
        user_properties = {
            'email': email,
            'password': password,
            'email_verified': False,
        }
        
        if display_name:
            user_properties['display_name'] = display_name
            
        user_record = auth.create_user(**user_properties)
        logger.info(f"✅ Firebase user created: {user_record.uid}")
        return user_record
    except auth.EmailAlreadyExistsError:
        logger.error(f"❌ Email already exists: {email}")
        return None
    except Exception as e:
        logger.error(f"❌ Failed to create Firebase user: {str(e)}")
        return None

# Initialize Firebase when the module is imported
logger.info("🚀 Initializing Firebase Admin SDK...")
firebase_initialized = initialize_firebase()

if firebase_initialized:
    logger.info("✅ Firebase Admin SDK initialized successfully")
else:
    logger.error("❌ Firebase Admin SDK initialization failed")
