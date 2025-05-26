# Backend/app/services/auth_service.py - FIXED VERSION
from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException, status
from app.models.user import UserCreate, PasswordResetRequest, PasswordReset, UserProfile
from app.core.security import get_password_hash, verify_password
from app.database import users_collection, password_reset_tokens_collection
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

def convert_objectid_to_str(doc: dict) -> dict:
    """Convert MongoDB ObjectId to string for JSON serialization"""
    if doc is None:
        return None
    
    # Create a copy to avoid modifying the original
    result = doc.copy()
    
    # Convert _id to string if it exists
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    
    # Convert any other ObjectId fields
    for key, value in result.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, list):
            result[key] = [str(item) if isinstance(item, ObjectId) else item for item in value]
        elif isinstance(value, dict):
            result[key] = convert_objectid_to_str(value)
    
    return result

async def get_or_create_user_by_firebase_uid(uid: str, email: str, display_name: str = None):
    """
    Get a user by Firebase UID or create a new one if not found.
    This ensures every user has a firebase_uid for proper data isolation.
    
    Args:
        uid: Firebase user ID (must be a string)
        email: User email
        display_name: User display name (optional)
        
    Returns:
        User document with ObjectIds converted to strings
    """
    # Validate inputs
    if not uid:
        logger.error("❌ Firebase UID is required")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase UID is required"
        )
        
    if not isinstance(uid, str):
        logger.error(f"❌ Invalid UID type: {type(uid)}, expected string. UID value: {uid}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UID format"
        )
        
    if not email:
        logger.error("❌ Email is required")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )
    
    try:
        logger.info(f"🔍 Looking for user with Firebase UID: {uid}")
        
        # Check if user exists by Firebase UID (primary lookup)
        user = await users_collection.find_one({"firebase_uid": uid})
        
        # If not found by UID, try to find by email (for migration cases)
        if not user:
            logger.info(f"🔍 User not found by UID, checking by email: {email}")
            user = await users_collection.find_one({"email": email})
            if user and not user.get("firebase_uid"):
                logger.info("🔄 Migrating existing user to Firebase UID")
                # Update existing user with Firebase UID (migration)
                await users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"firebase_uid": uid}}
                )
                user["firebase_uid"] = uid
        
        if user:
            logger.info(f"✅ Existing user found: {user.get('email')}")
            # User exists, update last login and other fields if needed
            update_fields = {"last_login": datetime.utcnow()}
            
            # Update display name if provided and different
            if display_name and display_name != user.get("full_name"):
                update_fields["full_name"] = display_name
                
            await users_collection.update_one(
                {"firebase_uid": uid},  # Use firebase_uid for consistent updates
                {"$set": update_fields}
            )
            
            # Update the user object with the new fields
            user.update(update_fields)
            
            # Convert ObjectId to string for JSON serialization
            return convert_objectid_to_str(user)
        
        logger.info(f"🆕 Creating new user for UID: {uid}")
        # User doesn't exist, create new user
        new_user = {
            "firebase_uid": uid,
            "email": email,
            "full_name": display_name or email.split("@")[0],
            "organization_name": None,
            "created_at": datetime.utcnow(),
            "last_login": datetime.utcnow(),
            "connected_accounts": [],
            "campaigns": [],  # Initialize empty campaigns
            "posts": [],      # Initialize empty posts
            "drafts": []      # Initialize empty drafts
        }
        
        result = await users_collection.insert_one(new_user)
        created_user = await users_collection.find_one({"_id": result.inserted_id})
        
        if not created_user:
            logger.error("❌ Failed to create user")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        
        logger.info("✅ New user created successfully")
        
        # Convert ObjectId to string for JSON serialization
        return convert_objectid_to_str(created_user)
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Error in get_or_create_user_by_firebase_uid: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request. Please try again."
        )

async def get_user_by_firebase_uid(uid: str) -> Optional[dict]:
    """
    Get a user by Firebase UID.
    
    Args:
        uid: Firebase user ID (must be a string)
        
    Returns:
        User document with ObjectIds converted to strings or None if not found
    """
    if not isinstance(uid, str):
        logger.error(f"❌ Invalid UID type: {type(uid)}, expected string")
        return None
        
    user = await users_collection.find_one({"firebase_uid": uid})
    if user:
        return convert_objectid_to_str(user)
    return None

async def update_user_profile(uid: str, profile_data: Dict[str, Any]) -> dict:
    """
    Update a user's profile data.
    
    Args:
        uid: Firebase user ID (must be a string)
        profile_data: Profile data to update
        
    Returns:
        Updated user document with ObjectIds converted to strings
    """
    if not isinstance(uid, str):
        logger.error(f"❌ Invalid UID type: {type(uid)}, expected string")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UID format"
        )
        
    user = await get_user_by_firebase_uid(uid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    
    # Add updated_at timestamp
    profile_data["updated_at"] = datetime.utcnow()
    
    # Update user profile using firebase_uid
    await users_collection.update_one(
        {"firebase_uid": uid},
        {"$set": profile_data}
    )
    
    # Get updated user
    updated_user = await get_user_by_firebase_uid(uid)
    return updated_user

# Legacy functions for backward compatibility
async def create_new_user(user_data: UserCreate) -> dict:
    """Legacy function for email/password registration"""
    hashed_password = get_password_hash(user_data.password)
    user_db_dict = {
        "full_name": user_data.full_name,
        "email": user_data.email,
        "organization_name": user_data.organization_name,
        "hashed_password": hashed_password,
        "created_at": datetime.utcnow(),
        "connected_accounts": [],
        "last_login": None,
        "campaigns": [],
        "posts": [],
        "drafts": []
    }
    
    try:
        result = await users_collection.insert_one(user_db_dict)
        created_user = await users_collection.find_one({"_id": result.inserted_id})
        if created_user:
            return convert_objectid_to_str(created_user)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user after creation."
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists."
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during user creation."
        )

async def verify_user_credentials(email: str, password: str) -> Optional[dict]:
    """Legacy function for email/password login"""
    user_db_doc = await users_collection.find_one({"email": email})
    if not user_db_doc:
        return None
    if not verify_password(password, user_db_doc["hashed_password"]):
        return None
    
    # Convert ObjectIds before returning
    return convert_objectid_to_str(user_db_doc)

async def request_password_reset(reset_request: PasswordResetRequest) -> dict:
    """Password reset functionality"""
    user = await users_collection.find_one({"email": reset_request.email})
    if not user:
        # Don't reveal if email exists
        return {"message": "If the email is registered, a reset link has been sent."}

    # Generate unique token
    token = str(uuid.uuid4())
    reset_doc = {
        "token": token,
        "user_id": user["_id"],
        "email": reset_request.email,
        "created_at": datetime.utcnow()
    }

    try:
        await password_reset_tokens_collection.insert_one(reset_doc)
    except DuplicateKeyError:
        # Rare case, regenerate token
        token = str(uuid.uuid4())
        reset_doc["token"] = token
        await password_reset_tokens_collection.insert_one(reset_doc)

    # Send email (implementation depends on your email service)
    # ... email sending logic ...

    return {"message": "If the email is registered, a reset link has been sent."}

async def reset_password(reset_data: PasswordReset) -> dict:
    """Reset password functionality"""
    token_doc = await password_reset_tokens_collection.find_one({"token": reset_data.token})
    if not token_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token."
        )

    user = await users_collection.find_one({"_id": token_doc["user_id"]})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found."
        )

    # Update password
    hashed_password = get_password_hash(reset_data.new_password)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"hashed_password": hashed_password}}
    )

    # Invalidate token
    await password_reset_tokens_collection.delete_one({"token": reset_data.token})

    return {"message": "Password reset successfully."}
