# app/services/content_planner_engine.py - FIXED VERSION WITH CORRECT DATE HANDLING
from datetime import datetime, timedelta
import json
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔧 Best recommended times for posting
RECOMMENDED_TIMES = ["10:00 AM", "12:00 PM", "3:00 PM", "6:00 PM"]


def generate_post_schedule(start_date_str: str, end_date_str: str, count: int):
    """
    Generate posting schedule with correct date distribution
    FIXED: Now properly distributes posts across the date range
    """
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

        if start_date > end_date:
            raise ValueError("Start date must be before end date.")

        total_days = (end_date - start_date).days + 1
        logger.info(f"📅 Scheduling {count} posts from {start_date_str} to {end_date_str} ({total_days} days)")

        scheduled_dates = []

        if count == 1:
            # Single post - use start date
            scheduled_dates = [start_date]
        elif count <= total_days:
            # Distribute posts evenly across the date range
            if count == 2:
                # For 2 posts, use start and end dates
                scheduled_dates = [start_date, end_date]
            else:
                # For more posts, distribute evenly
                interval = (total_days - 1) / (count - 1)
                for i in range(count):
                    days_offset = int(i * interval)
                    post_date = start_date + timedelta(days=days_offset)
                    scheduled_dates.append(post_date)
        else:
            # More posts than days - distribute with some posts on same days
            interval = total_days / count
            for i in range(count):
                days_offset = int(i * interval)
                if days_offset >= total_days:
                    days_offset = total_days - 1
                post_date = start_date + timedelta(days=days_offset)
                scheduled_dates.append(post_date)

        # Format dates with times
        scheduled_datetime = []
        for i, dt in enumerate(scheduled_dates):
            time_slot = RECOMMENDED_TIMES[i % len(RECOMMENDED_TIMES)]
            formatted_date = f"{dt.strftime('%B %d')} at {time_slot}"
            scheduled_datetime.append(formatted_date)
            logger.info(f"📌 Post {i + 1}: {formatted_date}")

        return scheduled_datetime

    except Exception as e:
        logger.error(f"❌ Error generating schedule: {e}")
        # Fallback to basic scheduling
        return [f"Day {i + 1} at 10:00 AM" for i in range(count)]


def create_fallback_content(campaign_name: str, theme: str, count: int, dates: list):
    """
    Create enhanced fallback content when Groq API fails.
    FIXED: Now uses the correct dates from the schedule
    """
    logger.info(f"Creating enhanced fallback content for campaign: {campaign_name}")

    # Enhanced content ideas based on theme
    content_ideas = {
        "sustainability": [
            "5 Simple Eco-Friendly Swaps for Your Daily Routine",
            "The Hidden Environmental Cost of Fast Fashion",
            "DIY Natural Cleaning Products That Actually Work",
            "How to Reduce Your Carbon Footprint in 30 Days",
            "Sustainable Travel Tips for the Eco-Conscious Explorer"
        ],
        "technology": [
            "AI Tools That Will Transform Your Workflow",
            "The Future of Remote Work Technology",
            "Cybersecurity Tips Every Professional Should Know",
            "Emerging Tech Trends to Watch This Year",
            "How to Automate Your Daily Tasks"
        ],
        "marketing": [
            "Content Marketing Strategies That Drive Results",
            "Social Media Trends Dominating 2025",
            "Email Marketing Mistakes to Avoid",
            "Building Brand Authority Through Thought Leadership",
            "ROI-Driven Digital Marketing Tactics"
        ],
        "food": [
            "Quick Healthy Meals for Busy Weekdays",
            "The Science Behind Food Cravings",
            "Local Ingredients That Boost Nutrition",
            "Meal Prep Strategies for Success",
            "Sustainable Eating on a Budget"
        ],
        "awareness": [
            "Breaking the Stigma: Understanding Mental Health",
            "The Science Behind Addiction and Recovery",
            "Supporting Loved Ones Through Difficult Times",
            "Evidence-Based Treatment Approaches",
            "Building Resilience and Recovery Communities"
        ]
    }

    content_types = ["Image Post", "Carousel", "Video/Reel", "Story"]
    calls_to_action = [
        "Save this post and try it out! Let us know your results in the comments 💭",
        "Share your experience with this in the comments below 👇",
        "Tag someone who needs to see this! 🏷️",
        "Double-tap if you agree and follow for more tips! ❤️",
        "What's your take on this? Join the conversation in the comments 💬"
    ]

    # Try to match theme keywords to get relevant content
    theme_lower = theme.lower()
    theme_key = None
    for key in content_ideas.keys():
        if key in theme_lower or any(word in theme_lower for word in key.split()):
            theme_key = key
            break

    if not theme_key:
        # Generic fallback based on theme
        base_ideas = [
            f"Top 5 {theme} Tips for Beginners",
            f"Common {theme} Mistakes to Avoid",
            f"The Ultimate {theme} Guide",
            f"{theme} Trends You Need to Know",
            f"How {theme} Can Transform Your Life"
        ]
    else:
        base_ideas = content_ideas[theme_key]

    fallback_content = []

    for i in range(count):
        content_type = content_types[i % len(content_types)]
        cta = calls_to_action[i % len(calls_to_action)]
        # FIXED: Use the actual scheduled date instead of generic "Day X"
        schedule = dates[i] if i < len(dates) else f"Day {i + 1} at 10:00 AM"

        # Get specific idea or create one
        if i < len(base_ideas):
            title = base_ideas[i]
        else:
            title = f"{theme} Insight #{i + 1}: Key Strategies and Tips"

        # Create detailed description based on content type
        if content_type == "Carousel":
            description = f"Create an engaging {content_type.lower()} showcasing '{title}'. Design 3-5 slides with clear, visual information. Use consistent branding with your color scheme. Include statistics, tips, or step-by-step guidance. Make each slide valuable and shareable."
        elif content_type == "Video/Reel":
            description = f"Produce a dynamic {content_type.lower()} about '{title}'. Keep it under 60 seconds with quick cuts and engaging visuals. Include text overlays for key points. Use trending audio and incorporate your brand personality. Focus on actionable takeaways."
        elif content_type == "Story":
            description = f"Create an interactive {content_type.lower()} series about '{title}'. Use polls, questions, or quizzes to engage viewers. Include behind-the-scenes content and personal insights. Add swipe-up links or action stickers for engagement."
        else:
            description = f"Design an eye-catching {content_type.lower()} featuring '{title}'. Use high-quality visuals with clear, readable text. Include your brand colors and fonts. Focus on one key message with supporting details. Make it scroll-stopping and shareable."

        post_content = {
            "post_number": i + 1,
            "title": title,
            "content_type": content_type,
            "schedule": schedule,  # This now contains the correct date
            "description": description,
            "call_to_action": cta,
            "theme": theme,
            "suggested_hashtags": f"#{theme.replace(' ', '').lower()} #socialmedia #content #marketing #tips",
            "notes": f"Enhanced fallback content for {campaign_name}"
        }
        fallback_content.append(post_content)

    return {
        "content_type": "enhanced_fallback",
        "generated_posts": fallback_content,
        "total_posts": count,
        "note": "Enhanced content generated using AI-powered fallback method."
    }


def serialize_crew_output(crew_output):
    """
    Convert CrewOutput object to a serializable format for MongoDB storage.
    """
    try:
        if isinstance(crew_output, (dict, str, int, float, bool, list)):
            return crew_output

        serialized = {}

        # Extract the raw text content
        if hasattr(crew_output, 'raw'):
            raw_content = str(crew_output.raw)
            serialized['raw'] = raw_content
            logger.info(f"Raw content length: {len(raw_content)}")
            logger.info(f"Raw content preview: {raw_content[:200]}...")

            # Try to parse structured content from raw text
            structured_posts = parse_crew_raw_content(raw_content)
            if structured_posts:
                serialized['generated_posts'] = structured_posts
                logger.info(f"Successfully parsed {len(structured_posts)} structured posts")

        # Extract other attributes
        if hasattr(crew_output, 'pydantic') and crew_output.pydantic:
            try:
                serialized['pydantic'] = crew_output.pydantic.model_dump()
            except Exception:
                serialized['pydantic'] = str(crew_output.pydantic)

        if hasattr(crew_output, 'json_dict') and crew_output.json_dict:
            serialized['json_dict'] = crew_output.json_dict

        if hasattr(crew_output, 'tasks_output') and crew_output.tasks_output:
            serialized['tasks_output'] = []
            for task_output in crew_output.tasks_output:
                task_data = {}
                if hasattr(task_output, 'raw'):
                    task_raw = str(task_output.raw)
                    task_data['raw'] = task_raw
                    logger.info(f"Task raw content: {task_raw[:200]}...")
                if hasattr(task_output, 'description'):
                    task_data['description'] = str(task_output.description)
                if hasattr(task_output, 'summary'):
                    task_data['summary'] = str(task_output.summary)
                if hasattr(task_output, 'agent'):
                    task_data['agent'] = str(task_output.agent)
                serialized['tasks_output'].append(task_data)

        if hasattr(crew_output, 'token_usage') and crew_output.token_usage:
            try:
                token_usage = crew_output.token_usage
                serialized['token_usage'] = {
                    'total_tokens': getattr(token_usage, 'total_tokens', 0),
                    'prompt_tokens': getattr(token_usage, 'prompt_tokens', 0),
                    'completion_tokens': getattr(token_usage, 'completion_tokens', 0)
                }
            except Exception:
                serialized['token_usage'] = str(crew_output.token_usage)

        if not serialized:
            serialized = {'raw': str(crew_output)}

        return serialized

    except Exception as e:
        logger.error(f"Error serializing crew output: {e}")
        return {'raw': str(crew_output), 'serialization_error': str(e)}


def parse_crew_raw_content(raw_content: str):
    """
    Parse CrewAI raw content and extract structured posts.
    FIXED: Better parsing to maintain schedule information
    """
    try:
        posts = []

        # Clean the content
        cleaned_content = raw_content.replace('**', '').replace('*', '').strip()
        logger.info(f"Parsing content: {cleaned_content[:500]}...")

        # Try multiple splitting patterns
        patterns = [
            r'Post\s+(\d+)(?:\s*[:.]?\s*\n)',  # "Post 1:"
            r'(\d+)[\.\)]\s*Post',  # "1. Post" or "1) Post"
            r'Post\s+(\d+)',  # "Post 1"
            r'(\d+)[\.\)]',  # "1." or "1)"
        ]

        sections = []

        for pattern in patterns:
            matches = list(re.finditer(pattern, cleaned_content, re.IGNORECASE | re.MULTILINE))
            if matches:
                logger.info(f"Found {len(matches)} matches with pattern: {pattern}")

                for i, match in enumerate(matches):
                    post_num = int(match.group(1))
                    start_pos = match.end()

                    # Find the end position (start of next post or end of content)
                    if i + 1 < len(matches):
                        end_pos = matches[i + 1].start()
                    else:
                        end_pos = len(cleaned_content)

                    content = cleaned_content[start_pos:end_pos].strip()
                    if content:
                        sections.append((post_num, content))

                if sections:
                    break  # Use the first pattern that works

        if not sections:
            logger.warning("No post sections found, trying line-by-line parsing")
            # Fallback: split by lines and look for numbered items
            lines = cleaned_content.split('\n')
            current_post = None
            current_content = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Check if line starts a new post
                post_match = re.match(r'^(?:Post\s+)?(\d+)[\.\):]?\s*', line)
                if post_match:
                    if current_post is not None and current_content:
                        sections.append((current_post, '\n'.join(current_content)))
                    current_post = int(post_match.group(1))
                    current_content = [line]
                elif current_post is not None:
                    current_content.append(line)

            if current_post is not None and current_content:
                sections.append((current_post, '\n'.join(current_content)))

        logger.info(f"Found {len(sections)} post sections")

        # Parse each section
        for post_num, content in sections:
            logger.info(f"Parsing post {post_num}: {content[:100]}...")
            post_data = parse_single_post_content(content, post_num)
            if post_data:
                posts.append(post_data)

        return posts if posts else None

    except Exception as e:
        logger.error(f"Error parsing crew raw content: {e}")
        return None


def parse_single_post_content(content: str, post_num: int):
    """
    Parse individual post content and extract structured data.
    FIXED: Better field extraction while preserving schedule information
    """
    try:
        lines = content.split('\n')

        post_data = {
            "post_number": post_num,
            "title": f"Post {post_num}",
            "content_type": "Image Post",
            "schedule": f"Day {post_num} at 10:00 AM",  # Default fallback
            "description": "",
            "call_to_action": "Engage with this post!",
            "theme": ""
        }

        current_field = None
        description_lines = []

        # Patterns for each field
        field_patterns = {
            'title': [
                r'^1\.\s*(?:What to Post|Title)[::]?\s*(.+)',
                r'^What to Post[::]?\s*(.+)',
                r'^Title[::]?\s*(.+)'
            ],
            'content_type': [
                r'^2\.\s*(?:Type of Post|Content Type|Post Type)[::]?\s*(.+)',
                r'^Type of Post[::]?\s*(.+)',
                r'^Content Type[::]?\s*(.+)'
            ],
            'schedule': [
                r'^3\.\s*(?:Posting Schedule|Schedule|Time)[::]?\s*(.+)',
                r'^Posting Schedule[::]?\s*(.+)',
                r'^Schedule[::]?\s*(.+)',
                # FIXED: Also look for date patterns in the content
                r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM))?'
            ],
            'description': [
                r'^4\.\s*(?:Description|Content|Details)[::]?\s*(.+)',
                r'^Description[::]?\s*(.+)',
                r'^Content[::]?\s*(.+)'
            ],
            'cta': [
                r'^5\.\s*(?:Call.to.Action|CTA|Call to Action)[::]?\s*(.+)',
                r'^Call.to.Action[::]?\s*(.+)',
                r'^CTA[::]?\s*(.+)'
            ]
        }

        for line in lines:
            line = line.strip()
            if not line:
                continue

            field_found = False

            # Check each field pattern
            for field_name, patterns in field_patterns.items():
                for pattern in patterns:
                    match = re.match(pattern, line, re.IGNORECASE)
                    if match:
                        value = match.group(1).strip() if match.groups() else line.strip()
                        if value:
                            if field_name == 'title':
                                post_data['title'] = value
                            elif field_name == 'content_type':
                                post_data['content_type'] = value
                            elif field_name == 'schedule':
                                post_data['schedule'] = value
                            elif field_name == 'description':
                                description_lines = [value]
                                current_field = 'description'
                            elif field_name == 'cta':
                                post_data['call_to_action'] = value
                        field_found = True
                        break
                if field_found:
                    break

            # If no field pattern matched and we're in description mode, add to description
            if not field_found and current_field == 'description' and line:
                description_lines.append(line)

        # Join description lines
        if description_lines:
            post_data['description'] = ' '.join(description_lines)

        # Ensure we have a description
        if not post_data['description'] or post_data['description'] == "":
            post_data[
                'description'] = f'Create engaging content for post {post_num}. Focus on delivering value to your audience.'

        logger.info(f"Parsed post {post_num}: {post_data['title']} - {post_data['schedule']}")
        return post_data

    except Exception as e:
        logger.error(f"Error parsing single post content: {e}")
        return None


def generate_content_plan(campaign_name: str, theme: str, count: int, start_date: str, end_date: str):
    """
    Generate content plan and return it in a MongoDB-serializable format.
    FIXED: Now properly handles date scheduling throughout the process
    """
    try:
        # FIXED: Generate the correct post schedule first
        post_schedule = generate_post_schedule(start_date, end_date, count)
        logger.info(f"Generated schedule: {post_schedule}")

        # Check if Groq API key is available
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key or not groq_api_key.startswith("gsk_"):
            logger.warning("Groq API key not available or invalid. Using enhanced fallback content generation.")

            fallback_result = create_fallback_content(campaign_name, theme, count, post_schedule)

            return {
                "postCount": count,
                "raw": fallback_result,
                "dates": post_schedule,
                "name": campaign_name,
                "theme": theme,
                "startDate": start_date,
                "endDate": end_date,
                "generation_method": "enhanced_fallback",
                "generated_posts": fallback_result["generated_posts"]
            }

        # Try to use CrewAI with Groq
        try:
            from ..agents.content_planner import ContentPlannerAgent
            from crewai import Crew

            logger.info(f"Attempting to generate content using CrewAI for campaign: {campaign_name}")

            planner_agent = ContentPlannerAgent()

            # FIXED: Pass the correct schedule to the agent
            task = planner_agent.create_planning_task(
                campaign_name=campaign_name,
                content_theme=theme,
                num_content_pieces=count,
                start_date=start_date,
                end_date=end_date,
                post_schedule=post_schedule
            )

            crew = Crew(
                agents=[task.agent],
                tasks=[task],
                verbose=True,
                memory=False,
                cache=False
            )

            result = crew.kickoff()

            # Serialize the CrewOutput object and extract structured posts
            serialized_result = serialize_crew_output(result)

            logger.info("CrewAI execution completed")

            # Extract generated posts from serialized result
            generated_posts = []
            if 'generated_posts' in serialized_result:
                generated_posts = serialized_result['generated_posts']
                logger.info(f"Found {len(generated_posts)} generated posts")
            elif serialized_result.get('raw'):
                # Try to parse from raw content
                parsed_posts = parse_crew_raw_content(str(serialized_result['raw']))
                if parsed_posts:
                    generated_posts = parsed_posts
                    logger.info(f"Parsed {len(generated_posts)} posts from raw content")

            # FIXED: Ensure posts have correct schedule information
            if generated_posts:
                for i, post in enumerate(generated_posts):
                    if i < len(post_schedule):
                        post['schedule'] = post_schedule[i]
                        logger.info(f"Updated post {i + 1} schedule to: {post_schedule[i]}")

            # If we still don't have good content, use enhanced fallback
            if not generated_posts or len(generated_posts) == 0:
                logger.warning("No structured posts extracted, using enhanced fallback")
                fallback_result = create_fallback_content(campaign_name, theme, count, post_schedule)
                generated_posts = fallback_result["generated_posts"]

            return {
                "postCount": count,
                "raw": serialized_result,
                "dates": post_schedule,
                "name": campaign_name,
                "theme": theme,
                "startDate": start_date,
                "endDate": end_date,
                "generation_method": "crewai_enhanced",
                "generated_posts": generated_posts
            }

        except Exception as crew_error:
            logger.error(f"CrewAI generation failed: {crew_error}")
            logger.info("Falling back to enhanced content generation")

            fallback_result = create_fallback_content(campaign_name, theme, count, post_schedule)

            return {
                "postCount": count,
                "raw": fallback_result,
                "dates": post_schedule,
                "name": campaign_name,
                "theme": theme,
                "startDate": start_date,
                "endDate": end_date,
                "generation_method": "fallback_after_error",
                "error": str(crew_error),
                "generated_posts": fallback_result["generated_posts"]
            }

    except Exception as e:
        logger.error(f"Error in generate_content_plan: {e}")

        try:
            post_schedule = generate_post_schedule(start_date, end_date, count)
        except Exception:
            post_schedule = [f"Day {i + 1} at 10:00 AM" for i in range(count)]

        fallback_result = create_fallback_content(campaign_name, theme, count, post_schedule)

        return {
            "postCount": count,
            "raw": fallback_result,
            "dates": post_schedule,
            "name": campaign_name,
            "theme": theme,
            "startDate": start_date,
            "endDate": end_date,
            "generation_method": "error_fallback",
            "error": str(e),
            "generated_posts": fallback_result["generated_posts"]
        }