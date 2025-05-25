# Backend/app/agents/content_planner.py - FIXED WITH PROPER DATE HANDLING
from crewai import Agent, Task
from typing import Dict, List
import os
from langchain_groq import ChatGroq


class ContentPlannerAgent:
    def __init__(self, groq_llm: ChatGroq = None):
        self.llm = groq_llm or self._create_groq_llm()

    def _create_groq_llm(self) -> ChatGroq:
        """Create Groq LLM instance with correct model format"""
        try:
            return ChatGroq(
                temperature=0.7,
                groq_api_key=os.getenv("GROQ_API_KEY"),
                model_name="groq/llama3-8b-8192",  # FIXED: Added groq/ prefix
                max_retries=3,
                request_timeout=60
            )
        except Exception as e:
            print(f"Error initializing Groq LLM: {e}")
            # Fallback to different model format
            try:
                return ChatGroq(
                    temperature=0.7,
                    groq_api_key=os.getenv("GROQ_API_KEY"),
                    model="llama3-8b-8192",  # Alternative format
                    max_retries=3,
                    request_timeout=60
                )
            except Exception as e2:
                print(f"Error with fallback model: {e2}")
                raise

    def create_agent(self) -> Agent:
        """Create content planner agent"""
        return Agent(
            role="Expert Social Media Content Strategist",
            goal="Create detailed, engaging social media content plans with specific topics, descriptions, and calls-to-action using the exact provided schedule",
            backstory="""You are a seasoned social media strategist with 10+ years of experience creating viral content. 
            You understand what makes content engaging across different platforms and can create detailed, actionable content plans.
            You always provide specific, detailed descriptions and compelling calls-to-action.
            You pay careful attention to the exact posting schedule provided and use those dates precisely.""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            max_iter=3
        )

    def create_planning_task(self, campaign_name: str, content_theme: str, num_content_pieces: int,
                             start_date: str = None, end_date: str = None, post_schedule: List[str] = None) -> Task:
        """
        Create content planning task with improved prompt and proper date handling
        FIXED: Now includes the exact schedule in the prompt
        """

        # Format the schedule information for the prompt
        schedule_info = ""
        if post_schedule and len(post_schedule) >= num_content_pieces:
            schedule_info = "\n\nUSE THESE EXACT POSTING SCHEDULES:\n"
            for i, schedule in enumerate(post_schedule[:num_content_pieces]):
                schedule_info += f"Post {i + 1}: {schedule}\n"
            schedule_info += "\nIMPORTANT: Use these exact dates and times in your '3. Posting Schedule' field for each post.\n"
        elif start_date and end_date:
            schedule_info = f"\n\nPosting period: {start_date} to {end_date}\n"

        return Task(
            description=f"""
Create a comprehensive content calendar for the '{campaign_name}' campaign focused on '{content_theme}'.

REQUIREMENTS:
- Generate exactly {num_content_pieces} unique posts
- Each post must have ALL 5 required fields filled out completely
- Provide specific, actionable content ideas (not generic descriptions)
- Include varied content types: Image Posts, Carousels (2-5 slides), Video/Reel ideas, Stories
- Make each post unique and engaging
{schedule_info}

For each post, you MUST provide:

Post [NUMBER]
1. What to Post: [Specific topic related to {content_theme} - be detailed and creative]
2. Type of Post: [Choose: Image Post, Carousel, Video/Reel, or Story]
3. Posting Schedule: [Use the EXACT schedule provided above for this post number]
4. Description: [Detailed description of the visual content, key points to highlight, and messaging strategy. This should be 2-3 sentences minimum with specific details about what the post should contain and how it should look]
5. Call-to-Action: [Specific, compelling CTA that drives engagement - not generic phrases]

EXAMPLE FORMAT:
Post 1
1. What to Post: Share 5 simple eco-friendly swaps for daily routines (reusable water bottles, bamboo toothbrushes, cloth shopping bags, LED bulbs, digital receipts)
2. Type of Post: Carousel
3. Posting Schedule: May 25 at 10:00 AM
4. Description: Create a visually appealing carousel showing before/after comparisons of wasteful vs. eco-friendly alternatives. Use bright, clean graphics with icons for each swap. Include statistics about environmental impact (e.g., "One reusable bottle saves 1,460 plastic bottles per year"). Use green and earth-tone color scheme.
5. Call-to-Action: Which eco-swap will you try first? Share your commitment in the comments and tag a friend to join the challenge!

CRITICAL INSTRUCTIONS:
- For the "Posting Schedule" field, use EXACTLY the schedule provided for each post number
- Do not make up your own dates or times
- If no specific schedule is provided, use the posting period information to create realistic dates
- Ensure each post has distinct, valuable content
- Focus on actionable insights and engaging content

Now create {num_content_pieces} posts following this exact format for the theme "{content_theme}":
            """,
            expected_output=f"A structured list of exactly {num_content_pieces} social media posts, each with all 5 required fields completely filled out with specific, detailed content and using the exact provided posting schedule",
            agent=self.create_agent()
        )