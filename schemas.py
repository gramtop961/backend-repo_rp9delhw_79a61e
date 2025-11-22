"""
Database Schemas for SmartScan AI

Each Pydantic model becomes a MongoDB collection (lowercased class name).
"""
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

GoalType = Literal["balanced", "weight_loss", "muscle_gain", "heart_health", "low_sugar"]
LanguageCode = Literal["en", "hi", "mr", "hinglish"]

class UserProfile(BaseModel):
    user_id: str = Field(..., description="Stable user identifier")
    name: Optional[str] = Field(None)
    goal: GoalType = Field("balanced")
    allergies: List[str] = Field(default_factory=list)
    sensitivities: List[str] = Field(default_factory=list)
    language: LanguageCode = Field("en")

class Nutrients(BaseModel):
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    sugar: Optional[float] = None
    fat: Optional[float] = None
    sat_fat: Optional[float] = None
    fiber: Optional[float] = None
    sodium: Optional[float] = None

class ScanItem(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    ingredients_text: Optional[str] = None
    nutrients: Optional[Nutrients] = None
    processing_level: Optional[str] = None

class Verdict(BaseModel):
    color: Literal["green", "yellow", "red"]
    score: int = Field(ge=0, le=100)
    explanation: str
    insulin_risk: Literal["low", "medium", "high"]

class Alternative(BaseModel):
    name: str
    brand: Optional[str] = None
    image_url: Optional[str] = None
    barcode: Optional[str] = None

class ScanRecord(BaseModel):
    user_id: str
    goal: GoalType
    item: ScanItem
    verdict: Verdict
    allergens_found: List[str] = Field(default_factory=list)
    alternatives: List[Alternative] = Field(default_factory=list)

class HealthScorePoint(BaseModel):
    user_id: str
    score: int = Field(ge=0, le=100)
    source_scan_id: Optional[str] = None

# Keep example schemas for reference compatibility
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = Field(None, ge=0, le=120)
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
