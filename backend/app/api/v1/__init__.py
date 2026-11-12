from fastapi import APIRouter

from .applications import router as applications_router
from .candidates import router as candidates_router
from .dashboard import router as dashboard_router
from .identity import router as identity_router
from .ingestion import router as ingestion_router
from .interviews import router as interviews_router
from .positions import router as positions_router
from .sync import router as sync_router
from .wecom import router as wecom_router
from .workbench import router as workbench_router

router = APIRouter()
router.include_router(identity_router)
router.include_router(positions_router)
router.include_router(candidates_router)
router.include_router(applications_router)
router.include_router(interviews_router)
router.include_router(ingestion_router)
router.include_router(dashboard_router)
router.include_router(sync_router)
router.include_router(workbench_router)
router.include_router(wecom_router)
