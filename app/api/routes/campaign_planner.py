# app/api/routes/campaign_planner.py - FIXED VERSION WITH PROPER DATE HANDLING
import traceback
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from app.services.content_planner_engine import generate_content_plan
from app.api.dependencies import auth_required
from app.database import campaign_schedules_collection, scheduled_posts_collection
from datetime import datetime, timedelta
from typing import List, Optional
from bson import ObjectId
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def parse_crew_output_to_posts(crew_output, campaign_name: str, theme: str, start_date: str, end_date: str,
                               post_schedule: List[str]):
    """
    Parse CrewAI output and convert it to structured posts
    FIXED: Now properly uses the provided post_schedule
    """
    posts = []

    try:
        # Extract raw content from crew output
        raw_content = ""
        if isinstance(crew_output, dict):
            if 'raw' in crew_output:
                raw_content = str(crew_output['raw'])
            elif 'generated_posts' in crew_output:
                # Handle fallback content structure
                for i, post in enumerate(crew_output['generated_posts']):
                    # FIXED: Use the correct schedule from post_schedule
                    schedule = post_schedule[i] if i < len(post_schedule) else f'Day {i + 1} at 10:00 AM'
                    posts.append({
                        'post_number': i + 1,
                        'title': post.get('title', f'Post {i + 1}'),
                        'content_type': post.get('content_type', 'Image Post'),
                        'schedule': schedule,  # Use the provided schedule
                        'description': post.get('description', ''),
                        'call_to_action': post.get('call_to_action', ''),
                        'theme': theme
                    })
                return posts
        elif hasattr(crew_output, 'raw'):
            raw_content = str(crew_output.raw)
        else:
            raw_content = str(crew_output)

        # Clean the content
        raw_content = raw_content.replace('**', '').replace('*', '').strip()

        # Split by post numbers
        post_sections = re.split(r'(?:^|\n)(?:Post\s+)?(\d+)[:\.]?\s*', raw_content, flags=re.MULTILINE)

        # Remove empty sections and pair numbers with content
        sections = []
        for i in range(1, len(post_sections), 2):
            if i + 1 < len(post_sections):
                post_num = post_sections[i]
                content = post_sections[i + 1].strip()
                if content:
                    sections.append((int(post_num), content))

        # If no numbered sections found, try alternative splitting
        if not sections:
            lines = raw_content.split('\n')
            current_post = None
            current_content = []

            for line in lines:
                line = line.strip()
                if re.match(r'^Post\s+\d+', line) or re.match(r'^\d+\.', line):
                    if current_post is not None:
                        sections.append((current_post, '\n'.join(current_content)))
                    current_post = len(sections) + 1
                    current_content = [line]
                elif current_post is not None:
                    current_content.append(line)

            if current_post is not None:
                sections.append((current_post, '\n'.join(current_content)))

        # Parse each section with correct scheduling
        for i, (post_num, content) in enumerate(sections):
            # FIXED: Use the provided schedule instead of calculating dates
            schedule = post_schedule[i] if i < len(post_schedule) else f'Day {i + 1} at 10:00 AM'

            # Parse content fields
            post_data = parse_post_content(content, post_num, theme, schedule)
            posts.append(post_data)

    except Exception as e:
        logger.error(f"Error parsing crew output: {e}")
        # Fallback: create basic posts with correct schedule
        for i in range(len(post_schedule) if post_schedule else 5):
            schedule = post_schedule[i] if i < len(post_schedule) else f'Day {i + 1} at 10:00 AM'
            posts.append({
                'post_number': i + 1,
                'title': f'{theme} - Post {i + 1}',
                'content_type': 'Image Post',
                'schedule': schedule,  # Use correct schedule
                'description': f'Content about {theme}. This is post {i + 1} in the {campaign_name} campaign.',
                'call_to_action': 'Engage with this post!',
                'theme': theme
            })

    return posts


def parse_post_content(content: str, post_num: int, theme: str, schedule: str):
    """
    Parse individual post content and extract fields
    FIXED: Now accepts schedule as parameter instead of calculating
    """
    lines = content.split('\n')

    # Initialize default values with provided schedule
    post_data = {
        'post_number': post_num,
        'title': f'{theme} - Post {post_num}',
        'content_type': 'Image Post',
        'schedule': schedule,  # Use the provided schedule
        'description': '',
        'call_to_action': 'Engage with this post!',
        'theme': theme
    }

    # Extract fields from content
    current_field = None
    description_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for field markers
        if re.match(r'^1\.\s*(?:What to Post|Title)[::]?\s*', line, re.IGNORECASE):
            title = re.sub(r'^1\.\s*(?:What to Post|Title)[::]?\s*', '', line, flags=re.IGNORECASE).strip()
            if title:
                post_data['title'] = title
            current_field = 'title'
        elif re.match(r'^2\.\s*(?:Type of Post|Content Type)[::]?\s*', line, re.IGNORECASE):
            content_type = re.sub(r'^2\.\s*(?:Type of Post|Content Type)[::]?\s*', '', line,
                                  flags=re.IGNORECASE).strip()
            if content_type:
                post_data['content_type'] = content_type
            current_field = 'type'
        elif re.match(r'^3\.\s*(?:Posting Schedule|Schedule)[::]?\s*', line, re.IGNORECASE):
            # FIXED: Extract the schedule if provided in content, but keep our provided schedule as fallback
            extracted_schedule = re.sub(r'^3\.\s*(?:Posting Schedule|Schedule)[::]?\s*', '', line,
                                        flags=re.IGNORECASE).strip()
            if extracted_schedule and extracted_schedule != schedule:
                # Only update if the extracted schedule looks like a real date/time
                if any(month in extracted_schedule for month in ['January', 'February', 'March', 'April', 'May', 'June',
                                                                 'July', 'August', 'September', 'October', 'November',
                                                                 'December']):
                    post_data['schedule'] = extracted_schedule
            current_field = 'schedule'
        elif re.match(r'^4\.\s*(?:Description|Content)[::]?\s*', line, re.IGNORECASE):
            desc = re.sub(r'^4\.\s*(?:Description|Content)[::]?\s*', '', line, flags=re.IGNORECASE).strip()
            if desc:
                description_lines = [desc]
            else:
                description_lines = []
            current_field = 'description'
        elif re.match(r'^5\.\s*(?:Call.to.Action|CTA)[::]?\s*', line, re.IGNORECASE):
            cta = re.sub(r'^5\.\s*(?:Call.to.Action|CTA)[::]?\s*', '', line, flags=re.IGNORECASE).strip()
            if cta:
                post_data['call_to_action'] = cta
            current_field = 'cta'
        elif current_field == 'description' and line:
            description_lines.append(line)

    # Join description lines
    if description_lines:
        post_data['description'] = '\n'.join(description_lines)

    # Ensure we have a description
    if not post_data['description']:
        post_data[
            'description'] = f'Create engaging content about {theme}. This is post {post_num} focusing on delivering value to your audience.'

    return post_data


def convert_schedule_to_datetime(schedule_str: str, start_date: str, post_index: int) -> datetime:
    """
    Convert schedule string to datetime object
    FIXED: Better parsing of schedule strings
    """
    try:
        # Try to parse if it contains month name
        if any(month in schedule_str for month in ['January', 'February', 'March', 'April', 'May', 'June',
                                                   'July', 'August', 'September', 'October', 'November', 'December']):
            # Parse format like "May 25 at 10:00 AM"
            import re
            date_match = re.search(r'(\w+)\s+(\d+)(?:\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM))?', schedule_str)
            if date_match:
                month_name, day, hour, minute, ampm = date_match.groups()

                # Convert month name to number
                month_map = {
                    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
                }
                month_num = month_map.get(month_name, 5)  # Default to May

                # Get year from start_date
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                year = start_dt.year

                # Handle hour conversion
                if hour and minute:
                    hour = int(hour)
                    minute = int(minute)
                    if ampm and ampm.upper() == 'PM' and hour != 12:
                        hour += 12
                    elif ampm and ampm.upper() == 'AM' and hour == 12:
                        hour = 0
                else:
                    hour, minute = 10, 0  # Default to 10:00 AM

                return datetime(year, month_num, int(day), hour, minute)

        # Fallback: calculate based on start date and post index
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        scheduled_date = start_dt + timedelta(days=post_index)
        return scheduled_date.replace(hour=10, minute=0, second=0)  # Default to 10 AM

    except Exception as e:
        logger.error(f"Error converting schedule '{schedule_str}': {e}")
        # Fallback to start date + index
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        return start_dt + timedelta(days=post_index)


@router.post("/plan-campaign/")
async def plan_campaign(data: dict, current_user_id: str = Depends(auth_required)):
    """
    Generate and store a content plan for a campaign with user-specific scoping.
    FIXED: Now properly creates individual posts with correct dates
    """
    try:
        # Validate input data
        required_fields = ["name", "theme", "count", "startDate", "endDate"]
        for field in required_fields:
            if field not in data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )

        # Validate data types and ranges
        try:
            post_count = int(data["count"])
            if post_count < 1 or post_count > 50:
                raise ValueError("Post count must be between 1 and 50")
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid post count. Must be a number between 1 and 50."
            )

        # Validate dates
        try:
            start_date = datetime.strptime(data["startDate"], '%Y-%m-%d')
            end_date = datetime.strptime(data["endDate"], '%Y-%m-%d')
            if start_date > end_date:
                raise ValueError("Start date must be before end date")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date format or range: {str(e)}"
            )

        # Generate content plan
        logger.info(f"Generating content plan for campaign: {data['name']}")
        result = generate_content_plan(
            campaign_name=data["name"],
            theme=data["theme"],
            count=post_count,
            start_date=data["startDate"],
            end_date=data["endDate"]
        )
        logger.info(f"Content plan generated, result type: {type(result)}")

        # Extract the schedule that was generated
        post_schedule = result.get('dates', [])
        logger.info(f"Generated schedule: {post_schedule}")

        # Parse CrewAI output into structured posts with correct schedule
        parsed_posts = []

        # First, try to get generated_posts directly from result
        if isinstance(result, dict) and 'generated_posts' in result:
            parsed_posts = result['generated_posts']
            logger.info(f"Using direct generated_posts: {len(parsed_posts)} posts")

            # FIXED: Ensure all posts have the correct schedule from post_schedule
            for i, post in enumerate(parsed_posts):
                if i < len(post_schedule):
                    post['schedule'] = post_schedule[i]
                    logger.info(f"Updated post {i + 1} schedule to: {post_schedule[i]}")
        else:
            # Fallback to parsing
            parsed_posts = parse_crew_output_to_posts(
                result,
                data["name"],
                data["theme"],
                data["startDate"],
                data["endDate"],
                post_schedule  # Pass the correct schedule
            )
            logger.info(f"Using parsed posts: {len(parsed_posts)} posts")

        # Ensure we have the right number of posts
        while len(parsed_posts) < post_count:
            i = len(parsed_posts)
            schedule = post_schedule[i] if i < len(post_schedule) else f'Day {i + 1} at 10:00 AM'
            parsed_posts.append({
                'post_number': i + 1,
                'title': f'{data["theme"]} - Post {i + 1}',
                'content_type': 'Image Post',
                'schedule': schedule,
                'description': f'Content about {data["theme"]}',
                'call_to_action': 'Engage with this post!',
                'theme': data["theme"]
            })

        # Trim to exact count
        parsed_posts = parsed_posts[:post_count]

        # Check if a similar campaign was recently created (within the last 5 minutes)
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        existing_campaign = await campaign_schedules_collection.find_one({
            "campaign_name": data["name"],
            "theme": data["theme"],
            "user_id": current_user_id,
            "created_at": {"$gte": five_minutes_ago}
        })

        if existing_campaign:
            logger.info(f"Found existing campaign with name '{data['name']}' created recently. Using that instead.")
            campaign_id = str(existing_campaign["_id"])
            # Update the existing campaign with the new data
            await campaign_schedules_collection.update_one(
                {"_id": existing_campaign["_id"]},
                {"$set": {
                    "updated_at": datetime.utcnow(),
                    "parsed_posts": parsed_posts,
                    "post_count": post_count
                }}
            )
        else:
            # Create campaign data
            campaign_data = {
                "campaign_name": data["name"],
                "theme": data["theme"],
                "start_date": data["startDate"],
                "end_date": data["endDate"],
                "user_id": current_user_id,
                "status": "draft",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "posts": result,  # Store original CrewAI output
                "parsed_posts": parsed_posts,  # Store structured posts
                "post_count": post_count
            }

            # Insert campaign into database
            campaign_result = await campaign_schedules_collection.insert_one(campaign_data)
            campaign_id = str(campaign_result.inserted_id)

        # Create individual post entries for the calendar with FIXED date handling
        posts_to_insert = []
        for i, post in enumerate(parsed_posts):
            # FIXED: Convert schedule string to proper datetime
            scheduled_datetime = convert_schedule_to_datetime(post['schedule'], data["startDate"], i)

            post_data = {
                "user_id": current_user_id,
                "campaign_id": campaign_id,
                "post_index": i,
                "title": post['title'],
                "caption": post['description'],
                "content": post['description'],
                "theme": data["theme"],
                "schedule": post['schedule'],  # Keep original schedule string
                "scheduled_time": scheduled_datetime,  # Proper datetime object
                "status": "scheduled",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "platform": "linkedin",  # Default platform
                "post_type": post['content_type'],
                "call_to_action": post['call_to_action'],
                "tags": [data["theme"], "campaign"]
            }
            posts_to_insert.append(post_data)
            logger.info(f"Post {i + 1} scheduled for: {scheduled_datetime} (from: {post['schedule']})")

        # Batch insert all posts
        if posts_to_insert:
            await scheduled_posts_collection.insert_many(posts_to_insert)

        return {
            "content": {
                "raw": result,
                "parsed_posts": parsed_posts,
                "postCount": post_count,
                "dates": post_schedule
            },
            "campaign_id": campaign_id,
            "message": f"Campaign '{data['name']}' created successfully with {post_count} posts",
            "success": True
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error("ERROR in /plan-campaign/:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while creating the campaign: {str(e)}"
        )


@router.get("/campaigns/")
async def get_user_campaigns(current_user_id: str = Depends(auth_required)):
    """Get all campaigns for the authenticated user ONLY."""
    try:
        cursor = campaign_schedules_collection.find({"user_id": current_user_id}).sort("created_at", -1)
        campaigns = await cursor.to_list(length=100)

        for campaign in campaigns:
            campaign["id"] = str(campaign.pop("_id"))
            if isinstance(campaign.get("created_at"), datetime):
                campaign["created_at"] = campaign["created_at"].isoformat()
            if isinstance(campaign.get("updated_at"), datetime):
                campaign["updated_at"] = campaign["updated_at"].isoformat()

        return {"campaigns": campaigns}

    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error("ERROR in /campaigns/:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching campaigns: {str(e)}"
        )


@router.get("/campaigns/{campaign_id}")
async def get_campaign_by_id(campaign_id: str, current_user_id: str = Depends(auth_required)):
    """Get a specific campaign by ID, ensuring it belongs to the authenticated user."""
    try:
        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid campaign ID format"
            )

        campaign = await campaign_schedules_collection.find_one({
            "_id": campaign_obj_id,
            "user_id": current_user_id
        })

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found or you don't have permission to access it"
            )

        campaign["id"] = str(campaign.pop("_id"))

        if isinstance(campaign.get("created_at"), datetime):
            campaign["created_at"] = campaign["created_at"].isoformat()
        if isinstance(campaign.get("updated_at"), datetime):
            campaign["updated_at"] = campaign["updated_at"].isoformat()

        return campaign

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error(f"ERROR in /campaigns/{campaign_id}:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching the campaign: {str(e)}"
        )


@router.get("/posts/")
async def get_user_posts(current_user_id: str = Depends(auth_required)):
    """Get all posts for the authenticated user ONLY."""
    try:
        cursor = scheduled_posts_collection.find({"user_id": current_user_id}).sort("created_at", -1)
        posts = await cursor.to_list(length=200)

        for post in posts:
            post["id"] = str(post.pop("_id"))
            if isinstance(post.get("created_at"), datetime):
                post["created_at"] = post["created_at"].isoformat()
            if isinstance(post.get("updated_at"), datetime):
                post["updated_at"] = post["updated_at"].isoformat()
            if isinstance(post.get("scheduled_time"), datetime):
                post["scheduled_time"] = post["scheduled_time"].isoformat()

        return {"posts": posts}

    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error("ERROR in /posts/:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching posts: {str(e)}"
        )


@router.get("/campaigns/{campaign_id}/posts")
async def get_campaign_posts(campaign_id: str, current_user_id: str = Depends(auth_required)):
    """Get all posts for a specific campaign, ensuring it belongs to the authenticated user."""
    try:
        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid campaign ID format"
            )

        campaign = await campaign_schedules_collection.find_one({
            "_id": campaign_obj_id,
            "user_id": current_user_id
        })

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found or you don't have permission to access it"
            )

        cursor = scheduled_posts_collection.find({
            "campaign_id": campaign_id,
            "user_id": current_user_id
        }).sort("post_index", 1)

        posts = await cursor.to_list(length=100)

        for post in posts:
            post["id"] = str(post.pop("_id"))
            if isinstance(post.get("created_at"), datetime):
                post["created_at"] = post["created_at"].isoformat()
            if isinstance(post.get("updated_at"), datetime):
                post["updated_at"] = post["updated_at"].isoformat()
            if isinstance(post.get("scheduled_time"), datetime):
                post["scheduled_time"] = post["scheduled_time"].isoformat()

        return {"posts": posts}

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error(f"ERROR in /campaigns/{campaign_id}/posts:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching campaign posts: {str(e)}"
        )


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, campaign_data: dict, current_user_id: str = Depends(auth_required)):
    """Update a campaign, ensuring it belongs to the authenticated user."""
    try:
        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid campaign ID format"
            )

        existing_campaign = await campaign_schedules_collection.find_one({
            "_id": campaign_obj_id,
            "user_id": current_user_id
        })

        if not existing_campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found or you don't have permission to update it"
            )

        update_data = {"updated_at": datetime.utcnow()}

        if "name" in campaign_data:
            update_data["campaign_name"] = campaign_data["name"]
        if "theme" in campaign_data:
            update_data["theme"] = campaign_data["theme"]
        if "start_date" in campaign_data:
            update_data["start_date"] = campaign_data["start_date"]
        if "end_date" in campaign_data:
            update_data["end_date"] = campaign_data["end_date"]
        if "status" in campaign_data:
            update_data["status"] = campaign_data["status"]

        await campaign_schedules_collection.update_one(
            {"_id": campaign_obj_id, "user_id": current_user_id},
            {"$set": update_data}
        )

        updated_campaign = await campaign_schedules_collection.find_one({
            "_id": campaign_obj_id,
            "user_id": current_user_id
        })
        updated_campaign["id"] = str(updated_campaign.pop("_id"))

        if isinstance(updated_campaign.get("created_at"), datetime):
            updated_campaign["created_at"] = updated_campaign["created_at"].isoformat()
        if isinstance(updated_campaign.get("updated_at"), datetime):
            updated_campaign["updated_at"] = updated_campaign["updated_at"].isoformat()

        return updated_campaign

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error(f"ERROR in updating campaign {campaign_id}:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while updating the campaign: {str(e)}"
        )


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, current_user_id: str = Depends(auth_required)):
    """Delete a campaign, ensuring it belongs to the authenticated user."""
    try:
        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid campaign ID format"
            )

        existing_campaign = await campaign_schedules_collection.find_one({
            "_id": campaign_obj_id,
            "user_id": current_user_id
        })

        if not existing_campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found or you don't have permission to delete it"
            )

        deleted_posts_result = await scheduled_posts_collection.delete_many({
            "campaign_id": campaign_id,
            "user_id": current_user_id
        })

        deleted_campaign_result = await campaign_schedules_collection.delete_one({
            "_id": campaign_obj_id,
            "user_id": current_user_id
        })

        return {
            "message": f"Campaign deleted successfully along with {deleted_posts_result.deleted_count} associated posts"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error(f"ERROR in deleting campaign {campaign_id}:", traceback_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while deleting the campaign: {str(e)}"
        )