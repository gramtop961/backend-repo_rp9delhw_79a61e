import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict, Any
import requests

from database import db, create_document, get_documents
from schemas import (
    UserProfile, ScanRecord, ScanItem, Verdict, Alternative,
    HealthScorePoint, GoalType
)

app = FastAPI(title="SmartScan AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- Helpers (placeholder logic; can be improved with external AI) --------
OPENFOODFACTS_API = "https://world.openfoodfacts.org/api/v2/product/"

class VerdictRequest(BaseModel):
    user_id: str
    goal: GoalType
    item: ScanItem


def compute_verdict(goal: GoalType, item: ScanItem) -> Verdict:
    # Simple heuristic: prioritize sugar for low_sugar/heart, protein for muscle, calories for weight
    score = 70
    insulin_risk: Literal["low", "medium", "high"] = "medium"

    if item.nutrients and item.nutrients.sugar is not None:
        sugar = item.nutrients.sugar
        if goal in ("low_sugar", "heart_health"):
            if sugar <= 5:
                score += 20; insulin_risk = "low"
            elif sugar <= 10:
                score += 0; insulin_risk = "medium"
            else:
                score -= 25; insulin_risk = "high"
    if item.nutrients and item.nutrients.protein is not None and goal == "muscle_gain":
        protein = item.nutrients.protein
        if protein >= 20:
            score += 15
        elif protein >= 10:
            score += 5
        else:
            score -= 10
    if item.nutrients and item.nutrients.calories is not None and goal == "weight_loss":
        c = item.nutrients.calories
        if c <= 150:
            score += 10
        elif c > 350:
            score -= 15

    score = max(0, min(100, score))
    color: Literal["green", "yellow", "red"] = "green" if score >= 75 else ("yellow" if score >= 55 else "red")

    # Micro explanation 8-12 words
    if color == "green":
        explanation = "Balanced nutrients; aligns well with your selected goal."
    elif color == "yellow":
        explanation = "Mixed profile; moderation advised based on your goal."
    else:
        explanation = "High risk factors for your goal; consider safer option."

    return Verdict(color=color, score=score, explanation=explanation, insulin_risk=insulin_risk)


def detect_allergens(ingredients_text: Optional[str], user_allergies: List[str]) -> List[str]:
    found = []
    if not ingredients_text:
        return found
    txt = ingredients_text.lower()
    for a in user_allergies:
        if a.lower() in txt:
            found.append(a)
    return found


def find_alternatives(item: ScanItem, goal: GoalType) -> List[Alternative]:
    # Grounded search via OpenFoodFacts categories/brands as a lightweight approach
    results: List[Alternative] = []
    try:
        query = item.brand or item.name or "healthy"
        url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={requests.utils.quote(query)}&json=1&page_size=5&tagtype_0=labels&tag_contains_0=contains&tag_0=organic"
        data = requests.get(url, timeout=6).json()
        for p in data.get("products", [])[:5]:
            results.append(Alternative(
                name=p.get("product_name") or "Alternative",
                brand=p.get("brands"),
                image_url=p.get("image_front_small_url") or p.get("image_url"),
                barcode=p.get("code"),
            ))
    except Exception:
        pass
    return results


# ------------------------------- API Routes -----------------------------------
@app.get("/")
def root():
    return {"message": "SmartScan AI Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set"
            response["database_name"] = getattr(db, 'name', '✅ Connected')
            response["connection_status"] = "Connected"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


@app.get("/api/barcode/{code}")
def barcode_lookup(code: str):
    try:
        r = requests.get(f"{OPENFOODFACTS_API}{code}.json", timeout=6)
        data = r.json()
        if data.get("status") != 1:
            raise HTTPException(status_code=404, detail="Product not found")
        p = data.get("product", {})
        item = ScanItem(
            name=p.get("product_name"),
            brand=p.get("brands"),
            barcode=p.get("code"),
            image_url=p.get("image_front_small_url") or p.get("image_url"),
            ingredients_text=p.get("ingredients_text"),
            nutrients={
                "calories": p.get("nutriments", {}).get("energy-kcal_100g"),
                "protein": p.get("nutriments", {}).get("proteins_100g"),
                "carbs": p.get("nutriments", {}).get("carbohydrates_100g"),
                "sugar": p.get("nutriments", {}).get("sugars_100g"),
                "fat": p.get("nutriments", {}).get("fat_100g"),
                "sat_fat": p.get("nutriments", {}).get("saturated-fat_100g"),
                "fiber": p.get("nutriments", {}).get("fiber_100g"),
                "sodium": p.get("nutriments", {}).get("sodium_100g"),
            },
            processing_level=p.get("nova_group"),
        )
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/verdict")
def generate_verdict(req: VerdictRequest):
    verdict = compute_verdict(req.goal, req.item)
    allergens = detect_allergens(req.item.ingredients_text, [])
    alternatives = find_alternatives(req.item, req.goal)

    record = ScanRecord(
        user_id=req.user_id,
        goal=req.goal,
        item=req.item,
        verdict=verdict,
        allergens_found=allergens,
        alternatives=alternatives,
    )
    scan_id = create_document("scanrecord", record)
    return {"scan_id": scan_id, "verdict": verdict, "allergens": allergens, "alternatives": alternatives}


class ProfileRequest(BaseModel):
    user_id: str

@app.post("/api/profile")
def get_or_create_profile(req: ProfileRequest):
    docs = get_documents("userprofile", {"user_id": req.user_id}, limit=1)
    if docs:
        doc = docs[0]
        doc["_id"] = str(doc["_id"])  # serialize
        return doc
    profile = UserProfile(user_id=req.user_id)
    _id = create_document("userprofile", profile)
    return {"_id": _id, **profile.model_dump()}


# Placeholder for image-based recognition route
@app.post("/api/scan/image")
async def scan_image(user_id: str, goal: GoalType, file: UploadFile = File(...)):
    # In a full build, send to a vision model. Here we return a stub item.
    item = ScanItem(name="Detected Meal", brand=None, image_url=None, ingredients_text="rice, chicken, spices", nutrients={"calories": 250, "protein": 18, "carbs": 30, "sugar": 2})
    verdict = compute_verdict(goal, item)
    allergens = detect_allergens(item.ingredients_text, [])
    alternatives = find_alternatives(item, goal)
    record = ScanRecord(user_id=user_id, goal=goal, item=item, verdict=verdict, allergens_found=allergens, alternatives=alternatives)
    scan_id = create_document("scanrecord", record)
    return {"scan_id": scan_id, "item": item, "verdict": verdict, "allergens": allergens, "alternatives": alternatives}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
