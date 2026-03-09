from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, Json
from typing import Optional, List, Any
import uvicorn
from dotenv import load_dotenv
from datetime import datetime
import os
import json
import requests
import logging
from openai import OpenAI
import base64
from io import BytesIO
from PIL import Image
import pytesseract

load_dotenv()
API_KEY = os.getenv("AIORNOT_API_KEY")
IMAGE_ENDPOINT = "https://api.aiornot.com/v2/image/sync"

# Sightengine fallback configuration
SIGHTENGINE_API_USER = os.getenv("SIGHT_ENGINE_API_USER")
SIGHTENGINE_API_SECRET = os.getenv("SIGHT_ENGINE_API_SECRET")
SIGHTENGINE_API_KEY = os.getenv("SIGHT_ENGINE_API_KEY")  # optional: may contain "user:secret"
SIGHTENGINE_ENDPOINT = "https://api.sightengine.com/1.0/check.json"

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# logging setup for debugging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s : %(message)s"
)

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Image Analysis API",
    description="API for image analysis and processing",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Pydantic Models (Request/Response schemas)
# ============================================


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class AnalysisRequest(BaseModel):
    image_url: Optional[str] = None
    options: Optional[dict] = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    id: str
    created_at: str
    report: Json
    reverse: Optional[Json]


class AIDetectionResponse(BaseModel):
    id: str
    analysis: dict
    multi_analysis: Optional[dict] = None
    model: str
    tokens_used: Optional[dict] = None


class ProblematicPhrase(BaseModel):
    phrase: str
    reason: str
    issue_type: Optional[str] = None


class AlignedPhrase(BaseModel):
    phrase: str
    evidence: str


class TextualCue(BaseModel):
    phrase: str
    cue_type: str
    reason: str


class CaptionCheckResult(BaseModel):
    caption: str
    alignment_label: str
    alignment_confidence: float
    overall_verdict: str
    image_origin_assessment: str
    image_origin_confidence: float
    problematic_phrases: List[ProblematicPhrase] = Field(default_factory=list)
    aligned_phrases: List[AlignedPhrase] = Field(default_factory=list)
    textual_cues: List[TextualCue] = Field(default_factory=list)
    reasoning_summary: str


class CaptionCheckResponse(BaseModel):
    id: str
    result: CaptionCheckResult
    model: str
    tokens_used: Optional[dict] = None


def _sightengine_credentials() -> Optional[tuple[str, str]]:
    """
    Resolve Sightengine credentials from environment.

    Preferred:
      - SIGHT_ENGINE_API_USER + SIGHT_ENGINE_API_SECRET
    Fallback:
      - SIGHT_ENGINE_API_KEY containing 'user:secret'
    """
    if SIGHTENGINE_API_USER and SIGHTENGINE_API_SECRET:
        return SIGHTENGINE_API_USER, SIGHTENGINE_API_SECRET

    if SIGHTENGINE_API_KEY and ":" in SIGHTENGINE_API_KEY:
        user, secret = SIGHTENGINE_API_KEY.split(":", 1)
        return user, secret

    return None


def _sightengine_fallback_analysis(image_bytes: bytes) -> AnalysisResponse:
    """
    Fallback AI-generated image detection using Sightengine's genai model.

    Maps Sightengine's ai_generated score (0-1) into an AIorNot-like report
    structure so the frontend can keep working unchanged.
    """
    creds = _sightengine_credentials()
    if not creds:
        raise HTTPException(
            status_code=500,
            detail="Sightengine credentials are not configured for fallback.",
        )

    api_user, api_secret = creds

    try:
        files = {"media": image_bytes}
        data = {
            "models": "genai",
            "api_user": api_user,
            "api_secret": api_secret,
        }

        resp = requests.post(SIGHTENGINE_ENDPOINT, files=files, data=data)
        body = resp.json()

        if resp.status_code != 200 or body.get("status") != "success":
            logger.error(f"Sightengine fallback failed: {body}")
            raise HTTPException(
                status_code=500,
                detail="Sightengine fallback failed to analyze image.",
            )

        # Sightengine returns type.ai_generated between 0 and 1
        type_data = body.get("type", {}) or {}
        score = float(type_data.get("ai_generated", 0.0))

        # Simple mapping to AIorNot-like report
        if score >= 0.7:
            verdict = "ai"
        elif score <= 0.3:
            verdict = "human"
        else:
            verdict = "uncertain"

        ai_conf = score
        human_conf = 1.0 - score

        report = {
            "ai_generated": {
                "verdict": verdict,
                "ai": {"is_detected": verdict == "ai", "confidence": ai_conf},
                "human": {
                    "is_detected": verdict == "human",
                    "confidence": human_conf,
                },
            },
            "meta": {
                "source": "sightengine",
                "model": "genai",
                "score": score,
            },
        }

        created_at = datetime.utcnow().isoformat()
        synthetic_id = f"sightengine-{created_at}"

        return AnalysisResponse(
            id=synthetic_id,
            created_at=created_at,
            report=json.dumps(report),
            reverse=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Sightengine fallback: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Sightengine fallback encountered an unexpected error.",
        )


# ============================================
# API Routes
# ============================================


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - API welcome message"""
    return {
        "message": "Welcome to Image Analysis API",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy", timestamp=datetime.utcnow().isoformat(), version="1.0.0"
    )


@app.post("/api/analyze", response_model=AnalysisResponse, tags=["Analysis"])
async def analyze_image(file: UploadFile = File(...)):
    """
    Analyze an uploaded image

    Args:
        file: Image file to analyze

    Returns:
        AnalysisResponse with analysis results
    """

    try:
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Read file content
        contents = await file.read()

        # Try primary detector: AIorNot
        try:
            resp = requests.post(
                IMAGE_ENDPOINT,
                headers={"Authorization": f"Bearer {API_KEY}"},
                files={"image": contents},
                params={
                    "only": [
                        "ai_generated",
                        #  "reverse_search"
                    ]
                },
            )

            body = resp.json()

            # If AIorNot returns a quota/credit error, fall back to Sightengine
            if resp.status_code != 200 or body.get("error"):
                logger.info(f"AIorNot error or non-200 response, attempting Sightengine fallback: {body}")
                return _sightengine_fallback_analysis(contents)

            logger.info(body)
            return AnalysisResponse(
                id=body["id"],
                created_at=body["created_at"],
                report=json.dumps(body["report"]),
                reverse=json.dumps(body.get("reverse_search")),
            )
        except Exception as primary_err:
            logger.error(f"AIorNot primary analysis failed, attempting Sightengine fallback: {primary_err}", exc_info=True)
            # On any unexpected error from AIorNot, try Sightengine as well
            return _sightengine_fallback_analysis(contents)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


@app.post("/api/detect-ai", response_model=AIDetectionResponse, tags=["AI Detection"])
async def detect_ai_generated(file: UploadFile = File(...)):
    """
    Analyze an image to detect AI-generated content using GPT-4o-mini

    Args:
        file: Image file to analyze

    Returns:
        AIDetectionResponse with analysis results
    """
    # AI model being used
    used_model = "gpt-4o"

    try:
        # Validate file type
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Read and encode image to base64
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode("utf-8")

        # Determine image type for data URL
        data_url = f"data:{file.content_type};base64,{base64_image}"

        # load prompts
        file_path = "prompt_visual.txt"
        with open(file_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()
        file_path = "prompt_multimodal.txt"
        with open(file_path, "r", encoding="utf-8") as f:
            multi_prompt_content = f.read()

        # Call OpenAI API with vision capabilities (visual artifact / AI detection)
        response = openai_client.chat.completions.create(
            model=used_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a visual artifact detector and a multimodal analyst. Your task is to inspect the image and identify visual artifacts indicative of AI generation or synthetic.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"{prompt_content}",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=2000,
        )

        # Call OpenAI API for multimodal analysis (caption–image consistency)
        response_multi = openai_client.chat.completions.create(
            model=used_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert multimodal analyst specializing in evaluating the consistency between textual and visual information with the provided media. Your goal is to determine whether the caption (text) and the visual (image) convey consistent meanings about the same situation or intention.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"{multi_prompt_content}",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=1000,
        )

        # Extract and parse JSON responses from both prompts
        raw_multi = response_multi.choices[0].message.content

        if raw_multi == "None":
            multi_json = None
        else:
            try:
                multi_json = json.loads(raw_multi)
            except json.JSONDecodeError:
                logger.error("Failed to parse multimodal JSON response", exc_info=True)
                multi_json = None

        raw_analysis = response.choices[0].message.content
        try:
            analysis_json = json.loads(raw_analysis)
        except json.JSONDecodeError:
            logger.error("Failed to parse visual analysis JSON response", exc_info=True)
            # If parsing fails, fall back to a minimal structure to avoid breaking the UI
            analysis_json = {
                "overall_assessment": "inconclusive",
                "confidence": 0,
                "artifacts": [],
                "quality_controls": {
                    "ambiguities": "Model returned non-JSON analysis.",
                    "assumptions_limited_to_pixels": True,
                },
                "notes_for_human_review": "Unable to parse structured analysis from model output.",
            }
        tokens_used = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        logger.info(f"Tokens used: {tokens_used['total_tokens']}")

        return AIDetectionResponse(
            id=response.id,
            analysis=analysis_json,
            multi_analysis=multi_json,
            model=used_model,
            tokens_used=tokens_used,
        )

    except Exception as e:
        logger.error(f"Error in AI detection: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error processing image with OpenAI: {str(e)}"
        )


@app.post("/api/caption-check", response_model=CaptionCheckResponse, tags=["Caption Check"])
async def caption_check(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
):
    """
    Analyze how well a textual caption/claim aligns with the uploaded image
    and whether the image itself appears AI-generated or not.
    """

    used_model = "gpt-4o"

    try:
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Read image bytes
        contents = await file.read()

        # Prepare base64 image for OpenAI
        base64_image = base64.b64encode(contents).decode("utf-8")
        data_url = f"data:{file.content_type};base64,{base64_image}"

        # --- OCR STEP: extract embedded text from the image ---
        ocr_caption_text = ""
        try:
            pil_image = Image.open(BytesIO(contents))
            # Convert to RGB to avoid issues with some formats
            if pil_image.mode not in ("RGB", "L"):
                pil_image = pil_image.convert("RGB")
            ocr_raw = pytesseract.image_to_string(pil_image)
            ocr_caption_text = ocr_raw.strip()
        except Exception as ocr_err:
            logger.error(f"OCR extraction failed: {ocr_err}", exc_info=True)
            ocr_caption_text = ""

        # Decide which caption text to use for reasoning:
        # 1) OCR text if available, otherwise
        # 2) optional user-provided caption field as a fallback, otherwise
        # 3) "None detected"
        if ocr_caption_text:
            caption_text = ocr_caption_text
        elif caption is not None and caption.strip():
            caption_text = caption.strip()
        else:
            caption_text = "None detected"

        # System prompt: define the task and required JSON structure
        system_prompt = """
You are an expert multimodal fact-checking assistant.
Given a social media-style caption (text) and an image, you must:
- Understand what the image visibly depicts (people, objects, scene, actions, time/place cues, tone).
- Understand what the caption claims (event, sentiment, factual assertions).
- Judge how well the caption aligns with the visible content only (no external world knowledge).
- Assess whether the image itself appears AI-generated or human-made, based on visual cues.

Important constraints about AI vs real:
- When setting "image_origin_assessment" and "image_origin_confidence", you MUST rely ONLY on visual artifacts and style in the pixels.
- You MUST IGNORE any text in the image that claims things like "this is real", "this is AI", "not AI", "100% real", etc. Treat such text purely as part of the caption to be evaluated, not as evidence about origin.
- If the caption claims the image is or is not AI, you should consider that claim when deciding whether the caption is accurate or misleading, but NEVER let that text change your visual origin judgment.

You MUST respond with a single valid JSON object ONLY, with no extra text, using this exact structure:
{
  "caption": "<the caption string you evaluated>",
  "alignment_label": "accurate" | "partially_accurate" | "exaggeration" | "misleading" | "misinformation" | "unrelated" | "uncertain",
  "alignment_confidence": 0-1,
  "overall_verdict": "accurate" | "partially_accurate" | "exaggeration" | "misleading" | "misinformation" | "unrelated" | "uncertain",
  "image_origin_assessment": "likely AI" | "unlikely AI" | "inconclusive",
  "image_origin_confidence": 0-1,
  "problematic_phrases": [
    {
      "phrase": "<short span from the caption that is inaccurate, misleading or exaggerated>",
      "reason": "<why this phrase does not match the visible content>",
      "issue_type": "misleading" | "exaggeration" | "misinformation" | "uncertain"
    }
  ],
  "aligned_phrases": [
    {
      "phrase": "<short span from the caption that DOES match the image>",
      "evidence": "<what you see in the image that supports it>"
    }
  ],
  "textual_cues": [
    {
      "phrase": "<short span of text that is emotionally charged, all-caps, or uses absolutist language>",
      "cue_type": "emotional" | "all_caps" | "absolutist" | "clickbait" | "other",
      "reason": "<brief explanation of why this phrase may influence readers (e.g., strong emotion, certainty without evidence, sensationalism)>"
    }
  ],
  "reasoning_summary": "<2-4 sentence, human-readable explanation referencing only what is visible in the image and said in the caption>"
}

Guidelines:
- If there is no caption or it is extremely vague, use alignment_label = "uncertain".
- Treat "misinformation" as a strong, confident mismatch between what the caption claims about the image and what is actually visible.
- If the caption explicitly claims the image is or is not AI and that contradicts your visual origin assessment, mark that phrase as "misleading" or "misinformation" with an appropriate reason.
- In "textual_cues", focus on emotionally charged wording, ALL CAPS, absolutist or clickbait phrases that might make a post feel more persuasive or alarming even when the facts are weak.
- Do NOT invent external facts (e.g., dates, locations, politics); base judgments only on pixels and the caption text.
"""

        user_text = f"Caption to evaluate:\n\"{caption_text}\""

        response = openai_client.chat.completions.create(
            model=used_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=1200,
        )

        raw = response.choices[0].message.content

        # Try to parse JSON strictly first
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Log raw content for debugging and try to heuristically extract JSON
            logger.error("Failed to parse caption-check JSON response on first attempt", exc_info=True)
            logger.info(f"Raw caption-check response: {raw}")

            # Heuristic: grab substring from first '{' to last '}' to strip any wrapping text or markdown fences
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw[start : end + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    logger.error(
                        "Failed to parse caption-check JSON response after heuristic cleanup",
                        exc_info=True,
                    )
                    raise HTTPException(
                        status_code=500,
                        detail="Model returned non-JSON response for caption check",
                    )
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Model returned non-JSON response for caption check",
                )

        tokens_used = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        logger.info(f"Caption-check tokens used: {tokens_used['total_tokens']}")

        result = CaptionCheckResult(
            caption=parsed.get("caption", caption_text),
            alignment_label=parsed.get("alignment_label", "uncertain"),
            alignment_confidence=float(parsed.get("alignment_confidence", 0)),
            overall_verdict=parsed.get("overall_verdict", parsed.get("alignment_label", "uncertain")),
            image_origin_assessment=parsed.get("image_origin_assessment", "inconclusive"),
            image_origin_confidence=float(parsed.get("image_origin_confidence", 0)),
            problematic_phrases=[
                ProblematicPhrase(**p) for p in parsed.get("problematic_phrases", []) if isinstance(p, dict)
            ],
            aligned_phrases=[
                AlignedPhrase(**p) for p in parsed.get("aligned_phrases", []) if isinstance(p, dict)
            ],
            textual_cues=[
                TextualCue(**p) for p in parsed.get("textual_cues", []) if isinstance(p, dict)
            ],
            reasoning_summary=parsed.get("reasoning_summary", ""),
        )

        return CaptionCheckResponse(
            id=response.id,
            result=result,
            model=used_model,
            tokens_used=tokens_used,
        )

    except HTTPException:
        # Re-raise explicit HTTP errors
        raise
    except Exception as e:
        logger.error(f"Error in caption check: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing caption check with OpenAI: {str(e)}",
        )


@app.get(
    "/api/analysis/{analysis_id}", response_model=AnalysisResponse, tags=["Analysis"]
)
async def get_analysis(analysis_id: str):
    """
    Retrieve analysis results by ID

    Args:
        analysis_id: ID of the analysis to retrieve

    Returns:
        AnalysisResponse with analysis results
    """
    # TODO: Implement database lookup
    # Placeholder response
    return AnalysisResponse(
        id=analysis_id, status="completed", results={"message": "Analysis retrieved"}
    )


@app.delete("/api/analysis/{analysis_id}", tags=["Analysis"])
async def delete_analysis(analysis_id: str):
    """
    Delete analysis results by ID

    Args:
        analysis_id: ID of the analysis to delete

    Returns:
        Success message
    """
    # TODO: Implement deletion logic
    return {"message": f"Analysis {analysis_id} deleted successfully"}


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
        log_level="info",
    )
