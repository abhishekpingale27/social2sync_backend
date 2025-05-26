# Backend/app/services/ai_engine.py - ENHANCED VERSION WITH GEMINI
import os
import requests
import json
from typing import Dict, List, Optional
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Fallback option

# Gemini API Configuration
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# SocialSync-specific system prompt
SOCIALSYNC_SYSTEM_PROMPT = """You are SocialSync AI, an advanced social media marketing assistant created specifically for the SocialSync platform. You are an expert in:

🎯 CORE EXPERTISE:
- Social media strategy and content planning
- Digital marketing campaigns and optimization
- Platform-specific best practices (Instagram, LinkedIn, Twitter, Facebook, TikTok)
- Content creation and copywriting
- Hashtag research and trending topics
- Audience engagement and growth strategies
- Social media analytics and performance optimization
- Influencer marketing and collaborations
- Brand building and personal branding
- Community management and customer service

📱 PLATFORM-SPECIFIC KNOWLEDGE:
- Instagram: Reels, Stories, IGTV, shopping features, algorithm insights
- LinkedIn: Professional content, thought leadership, company pages, LinkedIn ads
- Twitter/X: Trending topics, Twitter Spaces, thread strategies
- Facebook: Business pages, Facebook ads, community building
- TikTok: Viral content creation, trends, algorithm optimization
- YouTube: Video SEO, thumbnails, audience retention

🚀 CAPABILITIES:
- Generate viral content ideas tailored to specific niches
- Create engaging captions with optimal hashtags
- Develop comprehensive content calendars
- Suggest trending topics and challenges
- Provide platform-specific posting strategies
- Analyze content performance and suggest improvements
- Create ad copy and campaign strategies
- Offer crisis management advice
- Suggest collaboration and partnership opportunities

💡 RESPONSE STYLE:
- Be enthusiastic and creative while remaining professional
- Provide actionable, specific advice
- Include relevant hashtags, emojis, and formatting when appropriate
- Offer multiple options and variations
- Consider current trends and seasonal relevance
- Always think about ROI and business objectives

🎨 CONTENT CREATION FOCUS:
- Viral potential and engagement optimization
- Brand consistency and voice development
- Visual content suggestions (even though you can't see images)
- Cross-platform content adaptation
- User-generated content strategies
- Storytelling and narrative techniques

Remember: You're helping users grow their social media presence, increase engagement, drive conversions, and build authentic communities. Always provide practical, implementable advice that aligns with current social media best practices and trends.

Current date context: {current_date}
"""

class SocialSyncAI:
    def __init__(self):
        self.primary_api = "gemini" if GEMINI_API_KEY else "groq"
        logger.info(f"🤖 SocialSync AI initialized with {self.primary_api} as primary API")
    
    def _get_enhanced_prompt(self, user_query: str) -> str:
        """Create an enhanced prompt with context and current date"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Analyze query to provide context-specific responses
        query_lower = user_query.lower()
        context_hints = []
        
        # Add context based on query type
        if any(word in query_lower for word in ['instagram', 'ig', 'reel', 'story']):
            context_hints.append("Focus on Instagram-specific strategies and current features.")
        
        if any(word in query_lower for word in ['linkedin', 'professional', 'b2b']):
            context_hints.append("Emphasize professional networking and B2B strategies.")
        
        if any(word in query_lower for word in ['tiktok', 'viral', 'trending']):
            context_hints.append("Include trending formats and viral content strategies.")
        
        if any(word in query_lower for word in ['campaign', 'ads', 'advertising']):
            context_hints.append("Focus on paid advertising strategies and campaign optimization.")
        
        if any(word in query_lower for word in ['content calendar', 'planning', 'schedule']):
            context_hints.append("Provide structured planning and scheduling advice.")
        
        if any(word in query_lower for word in ['hashtag', 'tags', '#']):
            context_hints.append("Include specific hashtag strategies and trending tags.")
        
        # Seasonal context
        month = datetime.now().month
        if month in [11, 12, 1]:  # Holiday season
            context_hints.append("Consider holiday and year-end marketing opportunities.")
        elif month in [6, 7, 8]:  # Summer
            context_hints.append("Consider summer trends and vacation-related content.")
        
        enhanced_system_prompt = SOCIALSYNC_SYSTEM_PROMPT.format(current_date=current_date)
        
        if context_hints:
            enhanced_system_prompt += f"\n\n🎯 SPECIFIC CONTEXT FOR THIS QUERY:\n" + "\n".join([f"- {hint}" for hint in context_hints])
        
        return enhanced_system_prompt
    
    def _call_gemini_api(self, user_query: str) -> str:
        """Call Gemini API with enhanced prompting"""
        try:
            if not GEMINI_API_KEY:
                raise Exception("Gemini API key not configured")
            
            enhanced_prompt = self._get_enhanced_prompt(user_query)
            
            headers = {
                "Content-Type": "application/json",
            }
            
            # Gemini API payload structure
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": f"{enhanced_prompt}\n\nUser Query: {user_query}\n\nProvide a comprehensive, actionable response that helps the user achieve their social media marketing goals:"
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.8,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 1000,
                    "stopSequences": []
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    }
                ]
            }
            
            # Make API request
            url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract response from Gemini format
            if 'candidates' in data and len(data['candidates']) > 0:
                if 'content' in data['candidates'][0] and 'parts' in data['candidates'][0]['content']:
                    generated_text = data['candidates'][0]['content']['parts'][0]['text']
                    logger.info("✅ Gemini API response generated successfully")
                    return generated_text.strip()
            
            # Handle blocked content or other issues
            if 'candidates' in data and len(data['candidates']) > 0:
                finish_reason = data['candidates'][0].get('finishReason', 'UNKNOWN')
                if finish_reason == 'SAFETY':
                    return "I'd be happy to help with your social media marketing question! Could you please rephrase your query? I'm here to provide safe, professional marketing advice."
            
            raise Exception("No valid response from Gemini API")
            
        except requests.exceptions.Timeout:
            logger.error("⏰ Gemini API request timed out")
            raise Exception("Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Gemini API request failed: {e}")
            raise Exception(f"API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Gemini API error: {e}")
            raise Exception(f"Failed to generate response: {str(e)}")
    
    def _call_groq_api(self, user_query: str) -> str:
        """Fallback to GROQ API with enhanced prompting"""
        try:
            if not GROQ_API_KEY:
                raise Exception("GROQ API key not configured")
            
            enhanced_prompt = self._get_enhanced_prompt(user_query)
            
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "system", "content": enhanced_prompt},
                    {"role": "user", "content": user_query}
                ],
                "temperature": 0.8,
                "max_tokens": 1000,
                "top_p": 0.95,
                "stream": False
            }
            
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if 'choices' in data and len(data['choices']) > 0:
                generated_text = data['choices'][0]['message']['content']
                logger.info("✅ GROQ API response generated successfully")
                return generated_text.strip()
            
            raise Exception("No valid response from GROQ API")
            
        except requests.exceptions.Timeout:
            logger.error("⏰ GROQ API request timed out")
            raise Exception("Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ GROQ API request failed: {e}")
            raise Exception(f"API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"❌ GROQ API error: {e}")
            raise Exception(f"Failed to generate response: {str(e)}")
    
    def generate_response(self, user_query: str) -> str:
        """Generate AI response with fallback support"""
        if not user_query or not user_query.strip():
            return "👋 Hello! I'm your SocialSync AI assistant. How can I help you grow your social media presence today? Ask me about content ideas, strategies, trending topics, or any social media marketing questions!"
        
        try:
            # Try primary API first
            if self.primary_api == "gemini":
                try:
                    return self._call_gemini_api(user_query)
                except Exception as e:
                    logger.warning(f"⚠️ Gemini API failed, falling back to GROQ: {e}")
                    if GROQ_API_KEY:
                        return self._call_groq_api(user_query)
                    else:
                        raise e
            else:
                try:
                    return self._call_groq_api(user_query)
                except Exception as e:
                    logger.warning(f"⚠️ GROQ API failed, falling back to Gemini: {e}")
                    if GEMINI_API_KEY:
                        return self._call_gemini_api(user_query)
                    else:
                        raise e
                        
        except Exception as e:
            logger.error(f"❌ All AI APIs failed: {e}")
            
            # Provide helpful fallback response
            return f"""🤖 I'm temporarily experiencing technical difficulties, but I'm still here to help! 

Here are some quick social media tips while I get back online:

📱 **Content Ideas:**
- Share behind-the-scenes content
- Post user-generated content
- Create educational carousel posts
- Share industry insights and tips

📈 **Engagement Boosters:**
- Ask questions in your captions
- Use trending hashtags (research first!)
- Post when your audience is most active
- Respond to comments quickly

🎯 **Platform Tips:**
- Instagram: Focus on visual storytelling
- LinkedIn: Share professional insights
- TikTok: Jump on trending sounds/challenges
- Twitter: Engage in real-time conversations

Please try your question again in a moment, or contact our support team if the issue persists!

Error details: {str(e)}"""

# Create global instance
socialsync_ai = SocialSyncAI()

# Main function for backward compatibility
def generate_response(user_query: str) -> str:
    """Main function to generate AI responses"""
    return socialsync_ai.generate_response(user_query)
