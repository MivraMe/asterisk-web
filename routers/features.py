from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from database import AsyncSessionLocal
from models import Log
from services.asterisk_service import parse_features_conf, write_features_conf

router = APIRouter()


class FeatureWrite(BaseModel):
    name: str
    value: str
    section: str = "featuremap"


@router.get("/", summary="List all feature codes from features.conf")
async def list_features() -> dict:
    return parse_features_conf(settings.features_conf)


@router.put("/", summary="Overwrite features.conf with new data")
async def put_features(data: dict[str, dict[str, str]]) -> dict:
    write_features_conf(settings.features_conf, data)
    async with AsyncSessionLocal() as db:
        db.add(Log(level="INFO", message="Updated features.conf", module="features"))
        await db.commit()
    return {"status": "updated"}


@router.put("/{section}/{key}", summary="Set a single feature key")
async def set_feature(section: str, key: str, body: FeatureWrite) -> dict:
    data = parse_features_conf(settings.features_conf)
    data.setdefault(section, {})[key] = body.value
    write_features_conf(settings.features_conf, data)
    return {"status": "updated", "section": section, "key": key}


@router.delete("/{section}/{key}", summary="Remove a single feature key")
async def delete_feature(section: str, key: str) -> dict:
    data = parse_features_conf(settings.features_conf)
    if section not in data or key not in data[section]:
        raise HTTPException(status_code=404, detail=f"{section}/{key} not found")
    del data[section][key]
    write_features_conf(settings.features_conf, data)
    return {"status": "deleted"}
