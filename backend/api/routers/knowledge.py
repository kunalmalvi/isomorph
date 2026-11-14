"""Read-only seed knowledge endpoints. Data comes from data/ via the knowledge base loader and requires login."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from core.errors import NotFound
from database.models import User
from ..deps import current_user, pagination

router = APIRouter(tags=["knowledge"])


def _page(items: List[dict], p: dict) -> dict:
    return {"items": items[p["offset"]: p["offset"] + p["limit"]], "total": len(items), "limit": p["limit"], "offset": p["offset"]}


def _summary(s) -> dict:
    return {"id": s.id, "name": s.name, "domain": s.domain, "kind": s.kind, "summary": s.summary, "confidence": s.confidence,
            "node_count": len(s.graph.nodes), "edge_count": len(s.graph.edges), "sources": [x.to_dict() if hasattr(x, "to_dict") else x for x in s.sources]}


@router.get("/domains")
def list_domains(request: Request, user: User = Depends(current_user), p: dict = Depends(pagination)):
    kb = request.app.state.kb
    counts = {}
    for s in kb.systems:
        counts[s.domain] = counts.get(s.domain, 0) + 1
    items = [dict(d, system_count=counts.get(d["id"], 0)) for d in kb.domains_doc["domains"]]
    return _page(items, p)


def _domain(kb, domain_id: str) -> dict:
    d = next((d for d in kb.domains_doc["domains"] if d["id"] == domain_id), None)
    if d is None:
        raise NotFound("domain not found")
    return d


@router.get("/domains/{domain_id}")
def get_domain(domain_id: str, request: Request, user: User = Depends(current_user)):
    return _domain(request.app.state.kb, domain_id)


@router.get("/domains/{domain_id}/systems")
def domain_systems(domain_id: str, request: Request, user: User = Depends(current_user), p: dict = Depends(pagination)):
    kb = request.app.state.kb
    _domain(kb, domain_id)
    return _page([_summary(s) for s in kb.systems if s.domain == domain_id], p)


@router.get("/knowledge-systems")
def list_systems(request: Request, domain: Optional[str] = Query(None, max_length=60), q: Optional[str] = Query(None, max_length=100),
                 user: User = Depends(current_user), p: dict = Depends(pagination)):
    items = [s for s in request.app.state.kb.systems if (domain is None or s.domain == domain) and
             (q is None or q.lower() in (s.name + " " + s.summary).lower())]
    return _page([_summary(s) for s in items], p)


def _system(kb, system_id: str):
    s = kb.by_id.get(system_id)
    if s is None:
        raise NotFound("knowledge system not found")
    return s


@router.get("/knowledge-systems/{system_id}")
def get_system(system_id: str, request: Request, user: User = Depends(current_user)):
    return _system(request.app.state.kb, system_id).to_dict()


@router.get("/knowledge-systems/{system_id}/graph")
def system_graph(system_id: str, request: Request, user: User = Depends(current_user)):
    return _system(request.app.state.kb, system_id).graph.to_dict()


@router.get("/mechanisms")
def list_mechanisms(request: Request, domain: Optional[str] = Query(None, max_length=60), user: User = Depends(current_user),
                    p: dict = Depends(pagination)):
    kb = request.app.state.kb
    items = [s for s in kb.systems if s.id in kb.mechanism_ids and (domain is None or s.domain == domain)]
    return _page([_summary(s) for s in items], p)


@router.get("/mechanisms/{mechanism_id}")
def get_mechanism(mechanism_id: str, request: Request, user: User = Depends(current_user)):
    kb = request.app.state.kb
    if mechanism_id not in kb.mechanism_ids:
        raise NotFound("mechanism not found")
    return kb.by_id[mechanism_id].to_dict()
