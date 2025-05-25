# Backend/app/main.py - FIXED VERSION WITH PROPER DATETIME HANDLING
# IMPORTANT: Load environment variables FIRST before any other imports
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    # Get the path to the .env file (should be in the project root)
    env_path = Path(__file__).parent.parent / ".env"

    if env_path.exists():
        load_dotenv(env_path)
        print(f"[SUCCESS] Loaded environment variables from: {env_path}")
    else:
        print(f"[WARNING] .env file not found at: {env_path}")
        # Try loading from current directory
        load_dotenv()
        print("[SUCCESS] Attempted to load .env from current directory")

    # Debug: Print key environment variables
    print("[INFO] Key Environment Variables:")
    print(f"  FIREBASE_PROJECT_ID: {os.getenv('FIREBASE_PROJECT_ID')}")
    print(f"  FIREBASE_SERVICE_ACCOUNT_PATH: {os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')}")
    print(f"  MONGO_URI: {'SET' if os.getenv('MONGO_URI') else 'NOT SET'}")

except ImportError:
    print("[ERROR] python-dotenv not installed. Install with: pip install python-dotenv")
    print("[WARNING] Environment variables will only be loaded from system environment")

# Now import FastAPI and other modules
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import (
    chatbot,
    image_gen,
    caption_gen,
    drafts,
    post_now,
    campaign_planner,
    campaign_schedules,
    linkedin,
    accounts,
    auth,
    scheduled_posts
)
# Import authentication dependency
from app.api.dependencies import auth_required
from app.database import create_indexes, scheduled_posts_collection
from app.services.scheduler import start_scheduler, stop_scheduler
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from typing import List, Dict, Any
from app.database import db
import logging
import traceback
import pytz

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SocialSync AI Services")

# Enhanced CORS Middleware with more permissive settings for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development (restrict in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all headers
    max_age=86400  # Cache preflight requests for 24 hours
)

# Include routes
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chatbot.router, prefix="/api")
app.include_router(image_gen.router, prefix="/api")
app.include_router(caption_gen.router, prefix="/api")
app.include_router(drafts.router, prefix="/api")
app.include_router(campaign_planner.router, prefix="/api")
app.include_router(post_now.router, prefix="/api")
app.include_router(campaign_schedules.router, prefix="/api/campaign-schedules", tags=["Campaign Schedules"])
app.include_router(linkedin.router, prefix="/api/linkedin", tags=["LinkedIn"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["Accounts"])
app.include_router(scheduled_posts.router, prefix="/api", tags=["Scheduled Posts"])


@app.get("/")
def home():
    return {"message": "Welcome to SocialSync AI Services!"}


# Helper function to ensure datetime is timezone-aware (UTC)
def ensure_utc_datetime(dt):
    """Convert datetime to UTC timezone-aware datetime"""
    if dt is None:
        return None

    if isinstance(dt, str):
        # Parse string to datetime
        try:
            if dt.endswith('Z'):
                dt = dt.replace('Z', '+00:00')
            elif not dt.endswith(('+00:00', 'Z')) and 'T' in dt:
                dt = dt + '+00:00'
            dt = datetime.fromisoformat(dt)
        except ValueError as e:
            logger.error(f"❌ Error parsing datetime string: {dt}, error: {e}")
            raise ValueError(f"Invalid datetime format: {dt}")

    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC if not already
        dt = dt.astimezone(timezone.utc)

    return dt


def get_current_utc():
    """Get current UTC time as timezone-aware datetime"""
    return datetime.now(timezone.utc)


# FIXED: Proper schedule-post endpoint with proper datetime handling
@app.post("/api/schedule-post/")
async def schedule_post_endpoint(request_data: dict, current_user_id: str = Depends(auth_required)):
    """
    Schedule a post for future publishing with proper authentication and datetime handling.
    This endpoint handles individual post scheduling from the Calendar page.
    """
    try:
        logger.info(f"📅 Scheduling post for user {current_user_id}")
        logger.info(f"📋 Request data received: {list(request_data.keys())}")

        # Validate required fields
        if not request_data.get("caption"):
            logger.error("❌ Missing caption in request")
            raise HTTPException(
                status_code=400,
                detail="Caption is required"
            )

        if not request_data.get("platform"):
            logger.error("❌ Missing platform in request")
            raise HTTPException(
                status_code=400,
                detail="Platform is required"
            )

        if not request_data.get("scheduled_time"):
            logger.error("❌ Missing scheduled_time in request")
            raise HTTPException(
                status_code=400,
                detail="Scheduled time is required"
            )

        # FIXED: Parse the scheduled time with proper timezone handling
        try:
            scheduled_time_str = request_data["scheduled_time"]
            logger.info(f"🕐 Parsing scheduled time: {scheduled_time_str}")

            # Ensure we get a timezone-aware datetime in UTC
            scheduled_datetime = ensure_utc_datetime(scheduled_time_str)
            logger.info(f"✅ Parsed scheduled time: {scheduled_datetime} UTC")

        except ValueError as e:
            logger.error(f"❌ Time parsing error: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scheduled_time format. Expected ISO format, got: {request_data['scheduled_time']}"
            )

        # FIXED: Check if scheduled time is in the future using timezone-aware comparison
        now_utc = get_current_utc()
        logger.info(f"🕐 Current UTC time: {now_utc}")
        logger.info(f"🕐 Scheduled UTC time: {scheduled_datetime}")

        if scheduled_datetime <= now_utc:
            logger.warning(f"⚠️ Scheduled time {scheduled_datetime} is in the past (now: {now_utc})")
            # Allow scheduling up to 2 minutes in the past to handle timezone/latency issues
            time_diff = (now_utc - scheduled_datetime).total_seconds()
            if time_diff > 120:
                raise HTTPException(
                    status_code=400,
                    detail=f"Scheduled time must be in the future. Current time: {now_utc.isoformat()}, Scheduled: {scheduled_datetime.isoformat()}"
                )

        # Prepare the post data
        post_data = {
            "caption": request_data["caption"],
            "content": request_data["caption"],  # Add content field for compatibility
            "image_url": request_data.get("image_url"),
            "image_urls": [],
            "platform": request_data["platform"].lower(),
            "scheduled_time": scheduled_datetime,  # Store as timezone-aware datetime
            "is_carousel": request_data.get("is_carousel", False),
            "user_id": current_user_id,  # Use authenticated user ID
            "status": "scheduled",
            "created_at": get_current_utc(),  # Use timezone-aware datetime
            "updated_at": get_current_utc(),  # Use timezone-aware datetime
            "tags": request_data.get("tags", []),
            "assigned_to": None,
            "theme": "",
            "title": request_data["caption"][:100] if request_data["caption"] else "",
            "call_to_action": "",
            "source": "calendar",  # Mark this post as coming from the calendar
            "from_draft_id": request_data.get("from_draft_id")  # Track if it came from a draft
        }

        # Handle image_urls based on carousel status
        if request_data.get("image_url"):
            if request_data.get("is_carousel") and isinstance(request_data["image_url"], list):
                post_data["image_urls"] = request_data["image_url"]
                post_data["image_url"] = request_data["image_url"][0] if request_data["image_url"] else None
            else:
                post_data["image_urls"] = [request_data["image_url"]] if request_data["image_url"] else []

        logger.info(f"💾 Inserting post for platform: {post_data['platform']}")
        logger.info(f"📊 Post data prepared for user: {current_user_id}")

        # Insert into database
        result = await scheduled_posts_collection.insert_one(post_data)

        # Prepare response
        response_data = {
            "id": str(result.inserted_id),
            "message": "Post scheduled successfully",
            "scheduled_time": scheduled_datetime.isoformat(),
            "platform": request_data["platform"].lower(),
            "status": "scheduled",
            "caption": request_data["caption"],
            "image_url": request_data.get("image_url"),
            "is_carousel": request_data.get("is_carousel", False)
        }

        logger.info(f"✅ Post scheduled successfully with ID: {result.inserted_id}")
        return response_data

    except HTTPException as e:
        logger.error(f"❌ HTTP Error scheduling post: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"❌ Unexpected error scheduling post for user {current_user_id}: {str(e)}")
        traceback_str = traceback.format_exc()
        logger.error(f"Full traceback: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to schedule post: {str(e)}"
        )


# Debug endpoint for authentication testing
@app.get("/api/debug/auth")
async def debug_auth(authorization: Optional[str] = Header(None)):
    """Debug endpoint to test authentication"""
    result = {
        "authorization_header": authorization,
        "firebase_project_id": os.getenv("FIREBASE_PROJECT_ID"),
        "firebase_configured": bool(os.getenv("FIREBASE_PROJECT_ID")),
        "service_account_path": os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH"),
        "service_account_exists": os.path.exists(os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")),
    }

    if authorization:
        try:
            # Try to extract and verify token
            token = authorization.replace("Bearer ", "")
            result["token_preview"] = token[:20] + "..." if len(token) > 20 else token

            # Try to verify
            from app.core.firebase_admin import verify_firebase_token
            uid = verify_firebase_token(token)
            result["verification_result"] = uid
            result["verification_success"] = uid is not None

        except Exception as e:
            result["verification_error"] = str(e)
            result["verification_success"] = False

    return result


# FIXED: Stats endpoint with proper authentication
@app.get("/api/scheduled-posts-stats/")
async def get_scheduled_posts_stats(current_user_id: str = Depends(auth_required)):
    """Get statistics for scheduled posts for the authenticated user."""
    try:
        logger.info(f"📊 Getting stats for user: {current_user_id}")

        # Get posts for this user only
        cursor = scheduled_posts_collection.find({"user_id": current_user_id})
        posts = await cursor.to_list(length=None)

        total_posts = len(posts)
        by_platform = {}
        by_status = {}

        for post in posts:
            # Platform stats
            platform = post.get("platform", "unknown")
            by_platform[platform] = by_platform.get(platform, 0) + 1

            # Status stats
            status = post.get("status", "scheduled")
            by_status[status] = by_status.get(status, 0) + 1

        result = {
            "total_posts": total_posts,
            "by_platform": by_platform,
            "by_status": by_status
        }

        logger.info(f"📈 Stats for user {current_user_id}: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ Error getting stats for user {current_user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


# FIXED: Scheduled posts endpoint with proper authentication
@app.get("/api/scheduled-posts")
async def get_scheduled_posts(current_user_id: str = Depends(auth_required)):
    """Get all scheduled posts for the authenticated user."""
    try:
        logger.info(f"🔍 Fetching scheduled posts for user: {current_user_id}")

        # Find all posts for the current user only
        cursor = scheduled_posts_collection.find({"user_id": current_user_id}).sort("scheduled_time", 1)
        posts = await cursor.to_list(length=200)

        logger.info(f"📊 Found {len(posts)} scheduled posts for user {current_user_id}")

        # Convert ObjectId to string and format dates
        processed_posts = []
        for post in posts:
            # FIXED: Handle datetime serialization properly
            scheduled_time = post.get("scheduled_time")
            created_at = post.get("created_at")
            updated_at = post.get("updated_at")

            # Convert datetimes to ISO format strings
            if isinstance(scheduled_time, datetime):
                scheduled_time = scheduled_time.isoformat()
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            if isinstance(updated_at, datetime):
                updated_at = updated_at.isoformat()

            processed_post = {
                "id": str(post["_id"]),
                "caption": post.get("caption", post.get("content", "")),
                "content": post.get("content", post.get("caption", "")),
                "image_url": post.get("image_url"),
                "image_urls": post.get("image_urls", [post.get("image_url")] if post.get("image_url") else []),
                "platform": post.get("platform", "unknown"),
                "scheduled_time": scheduled_time,
                "status": post.get("status", "scheduled"),
                "is_carousel": post.get("is_carousel", False),
                "user_id": post.get("user_id"),
                "created_at": created_at,
                "updated_at": updated_at,
                "tags": post.get("tags", []),
                "assigned_to": post.get("assigned_to"),
                "theme": post.get("theme", ""),
                "title": post.get("title", ""),
                "call_to_action": post.get("call_to_action", "")
            }
            processed_posts.append(processed_post)

        return {"posts": processed_posts}

    except Exception as e:
        logger.error(f"❌ Error getting posts for user {current_user_id}: {e}")
        traceback_str = traceback.format_exc()
        logger.error(f"Full traceback: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get scheduled posts: {str(e)}"
        )


@app.get("/api/team-members")
async def get_team_members():
    """Get team members (mock data for now)."""
    try:
        # In a real app, you would fetch from your database
        # For now, returning mock data
        return [
            {"id": "1", "username": "user1", "name": "John Doe"},
            {"id": "2", "username": "user2", "name": "Jane Smith"},
            {"id": "3", "username": "user3", "name": "Bob Johnson"}
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch team members: {str(e)}")


# FIXED: Delete endpoint with proper authentication
@app.delete("/api/scheduled-posts/{post_id}")
async def delete_scheduled_post(post_id: str, current_user_id: str = Depends(auth_required)):
    """Delete a scheduled post, ensuring it belongs to the authenticated user."""
    try:
        logger.info(f"🗑️ Attempting to delete post {post_id} for user {current_user_id}")

        # Delete only if the post belongs to the current user
        result = await scheduled_posts_collection.delete_one({
            "_id": ObjectId(post_id),
            "user_id": current_user_id
        })

        if result.deleted_count == 0:
            logger.warning(f"⚠️ Post {post_id} not found or doesn't belong to user {current_user_id}")
            raise HTTPException(
                status_code=404,
                detail="Post not found or you don't have permission to delete it"
            )

        logger.info(f"✅ Successfully deleted post {post_id}")
        return {"message": "Post deleted successfully"}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Error deleting post {post_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete post: {str(e)}")


# FIXED: Update endpoint with proper authentication and datetime handling
@app.patch("/api/scheduled-posts/{post_id}")
async def update_scheduled_post(post_id: str, update_data: Dict[str, Any],
                                current_user_id: str = Depends(auth_required)):
    """Update a scheduled post, ensuring it belongs to the authenticated user."""
    try:
        logger.info(f"🔧 Updating post {post_id} for user {current_user_id}")

        # Remove None values from update data
        clean_update_data = {k: v for k, v in update_data.items() if v is not None}

        if not clean_update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")

        # FIXED: Handle datetime fields properly
        if "scheduled_time" in clean_update_data:
            clean_update_data["scheduled_time"] = ensure_utc_datetime(clean_update_data["scheduled_time"])

        # Add updated_at timestamp
        clean_update_data["updated_at"] = get_current_utc()

        # Update only if the post belongs to the current user
        result = await scheduled_posts_collection.update_one(
            {"_id": ObjectId(post_id), "user_id": current_user_id},
            {"$set": clean_update_data}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Post not found or you don't have permission to update it"
            )

        logger.info(f"✅ Successfully updated post {post_id}")
        return {"message": "Post updated successfully"}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"❌ Error updating post {post_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update post: {str(e)}")


@app.on_event("startup")
async def startup_db_client():
    await create_indexes()
    await start_scheduler()


@app.on_event("shutdown")
async def shutdown_scheduler():
    await stop_scheduler()


@app.get("/status")
async def status():
    return {
        "status": "operational",
        "environment": {
            "firebase_project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "firebase_configured": bool(os.getenv("FIREBASE_PROJECT_ID")),
            "mongo_configured": bool(os.getenv("MONGO_URI")),
        },
        "services": {
            "scheduler": "active",
            "gemini": True,
            "groq": True,
            "huggingface": True,
            "advanced_huggingface": True,
            "linkedin": True,
            "firebase": bool(os.getenv("FIREBASE_PROJECT_ID")),
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)