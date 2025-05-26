# Backend/app/api/routes/chatbot.py - ENHANCED VERSION
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.services.ai_engine import generate_response
from app.api.dependencies import auth_required, optional_auth
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime
import asyncio

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Enhanced request models
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User's chat message")
    context: Optional[str] = Field(None, description="Additional context about user's business/niche")
    conversation_id: Optional[str] = Field(None, description="Conversation identifier for context")
    
class QuickSuggestionRequest(BaseModel):
    category: str = Field(..., description="Category of suggestions (content_ideas, captions, hashtags, etc.)")
    niche: Optional[str] = Field(None, description="User's business niche or industry")
    platform: Optional[str] = Field(None, description="Target social media platform")

class ChatResponse(BaseModel):
    response: str
    suggestions: Optional[List[str]] = None
    conversation_id: str
    timestamp: str
    response_time: Optional[float] = None

@router.post("/chatbot/", response_model=ChatResponse)
async def chatbot_endpoint(
    chat: ChatRequest, 
    current_user_id: Optional[str] = Depends(optional_auth)
):
    """
    Enhanced chatbot endpoint with user authentication and improved responses.
    Provides SocialSync-specific AI assistance for social media marketing.
    """
    start_time = datetime.now()
    
    try:
        logger.info(f"🤖 Processing chat request for user: {current_user_id or 'anonymous'}")
        logger.info(f"📝 Query preview: {chat.query[:100]}...")
        
        # Validate input
        if not chat.query.strip():
            raise HTTPException(
                status_code=400, 
                detail="Query cannot be empty. Please ask me something about social media marketing!"
            )
        
        # Enhanced query with context if provided
        enhanced_query = chat.query
        if chat.context:
            enhanced_query = f"Context about my business: {chat.context}\n\nQuestion: {chat.query}"
        
        # Generate AI response
        response_text = await asyncio.get_event_loop().run_in_executor(
            None, generate_response, enhanced_query
        )
        
        # Calculate response time
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds()
        
        # Generate conversation ID if not provided
        conversation_id = chat.conversation_id or f"conv_{int(datetime.now().timestamp())}"
        
        # Extract suggestions if any (look for bulleted lists in response)
        suggestions = []
        if "•" in response_text or "◦" in response_text or "-" in response_text:
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith(('•', '◦', '-', '*')) and len(line) > 3:
                    clean_suggestion = line.lstrip('•◦-*').strip()
                    if clean_suggestion and len(clean_suggestion) < 200:
                        suggestions.append(clean_suggestion)
        
        # Log successful response
        logger.info(f"✅ Response generated in {response_time:.2f}s for user: {current_user_id or 'anonymous'}")
        
        return ChatResponse(
            response=response_text,
            suggestions=suggestions[:5] if suggestions else None,  # Limit to 5 suggestions
            conversation_id=conversation_id,
            timestamp=end_time.isoformat(),
            response_time=response_time
        )
        
    except HTTPException as e:
        logger.error(f"❌ HTTP error in chatbot: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"❌ Unexpected error in chatbot: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="I'm experiencing technical difficulties. Please try again in a moment!"
        )

@router.post("/chatbot/quick-suggestions/")
async def get_quick_suggestions(
    request: QuickSuggestionRequest,
    current_user_id: Optional[str] = Depends(optional_auth)
):
    """
    Get quick suggestions for common social media needs.
    """
    try:
        logger.info(f"🚀 Quick suggestions requested: {request.category} for {request.niche or 'general'}")
        
        # Build query based on category
        query_templates = {
            "content_ideas": f"Generate 5 engaging content ideas for {request.niche or 'a business'} on {request.platform or 'social media'}",
            "captions": f"Write 3 engaging captions for {request.niche or 'a business'} posts on {request.platform or 'social media'}",
            "hashtags": f"Suggest 15 relevant hashtags for {request.niche or 'a business'} on {request.platform or 'social media'}",
            "posting_times": f"What are the best posting times for {request.platform or 'social media'} in {request.niche or 'general business'}?",
            "engagement_tips": f"Give me 5 tips to increase engagement on {request.platform or 'social media'} for {request.niche or 'my business'}",
            "trending_topics": f"What are some trending topics and content formats for {request.platform or 'social media'} that {request.niche or 'businesses'} can use?",
            "campaign_ideas": f"Suggest 3 creative marketing campaign ideas for {request.niche or 'a business'} on {request.platform or 'social media'}"
        }
        
        query = query_templates.get(
            request.category, 
            f"Give me social media advice for {request.category} related to {request.niche or 'my business'}"
        )
        
        # Generate response
        response_text = await asyncio.get_event_loop().run_in_executor(
            None, generate_response, query
        )
        
        return {
            "category": request.category,
            "niche": request.niche,
            "platform": request.platform,
            "suggestions": response_text,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating quick suggestions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate suggestions. Please try again!"
        )

@router.get("/chatbot/health/")
async def chatbot_health_check():
    """
    Health check endpoint for the chatbot service.
    """
    try:
        # Test AI service
        test_response = await asyncio.get_event_loop().run_in_executor(
            None, generate_response, "Hello, this is a health check."
        )
        
        return {
            "status": "healthy",
            "ai_service": "operational",
            "timestamp": datetime.now().isoformat(),
            "test_response_length": len(test_response)
        }
    except Exception as e:
        logger.error(f"❌ Chatbot health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "ai_service": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@router.get("/chatbot/capabilities/")
async def get_chatbot_capabilities():
    """
    Get information about the chatbot's capabilities.
    """
    return {
        "name": "SocialSync AI Assistant",
        "version": "2.0",
        "capabilities": [
            "Social media strategy planning",
            "Content idea generation",
            "Caption and copy writing",
            "Hashtag research and suggestions",
            "Platform-specific advice",
            "Trend analysis and recommendations",
            "Engagement optimization tips",
            "Campaign planning and execution",
            "Brand building strategies",
            "Analytics interpretation",
            "Crisis management advice",
            "Influencer collaboration tips"
        ],
        "supported_platforms": [
            "Instagram",
            "LinkedIn", 
            "Twitter/X",
            "Facebook",
            "TikTok",
            "YouTube",
            "Pinterest"
        ],
        "features": [
            "Context-aware responses",
            "Multi-platform strategies",
            "Real-time trend integration",
            "Personalized recommendations",
            "Seasonal content suggestions",
            "Industry-specific advice",
            "ROI-focused strategies"
        ],
        "response_formats": [
            "Detailed explanations",
            "Step-by-step guides",
            "Bulleted action items",
            "Template examples",
            "Quick tips and tricks"
        ]
    }
