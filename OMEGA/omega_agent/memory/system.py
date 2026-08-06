"""Unified memory facade with FAISS, preferences, and audit - FULLY CAPABLE VERSION."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from omega_agent.core.config import Config
from omega_agent.core.types import AgentResult
from omega_agent.memory.episodic import EpisodicMemory, EpisodicRecord
from omega_agent.memory.semantic import SemanticMemory
from omega_agent.memory.knowledge_graph import KnowledgeGraph
from omega_agent.memory.embeddings import EmbeddingMemory
from omega_agent.memory.preferences import UserPreferences
from omega_agent.memory.audit import AuditTrail

logger = logging.getLogger("omega_agent.memory")


class MemorySystem:
    """
    Unified memory: episodic + semantic + FAISS + preferences + audit.
    
    FULLY FUNCTIONAL - supports:
    ✅ Store episodic experiences
    ✅ Retrieve similar past experiences  
    ✅ Query semantic knowledge by domain
    ✅ Traverse knowledge graph relationships
    ✅ Vector similarity search (if FAISS available)
    ✅ User preference persistence and retrieval
    ✅ Immutable audit trail
    """

    def __init__(self, config: Config):
        self.config = config
        self.episodic = EpisodicMemory(config.memory_db_path)
        self.semantic = SemanticMemory(config) if config.enable_semantic_memory else None
        self.knowledge_graph = KnowledgeGraph(config)
        self.embeddings = EmbeddingMemory() if config.enable_faiss else None
        self.preferences = UserPreferences(config)
        self.audit = AuditTrail(config)
        logger.info("MemorySystem initialized (faiss=%s, semantic=%s)", 
                   bool(self.embeddings and self.embeddings.enabled),
                   bool(self.semantic))

    # ============ STORE OPERATIONS ============
    
    async def save_result(
        self,
        goal: str,
        domain: str,
        result: AgentResult,
    ) -> None:
        """Save execution result to all memory layers."""
        if self.config.enable_episodic_memory:
            self.episodic.save(EpisodicRecord(
                goal=goal,
                result=result.to_dict(),
                metadata={"domain": domain, "success": result.success},
            ))

        if result.decision and self.semantic:
            await self.semantic.store(
                domain,
                f"action_{result.decision.action}",
                {
                    "confidence": result.decision.confidence,
                    "goal_prefix": goal[:100],
                    "best_practices_used": result.metadata.get("best_practices", []),
                },
                confidence=result.decision.confidence,
            )

        if self.embeddings and self.embeddings.enabled:
            self.embeddings.add(
                f"{goal} -> {result.output[:500]}",
                {"domain": domain, "success": result.success, "action": result.decision.action if result.decision else None},
            )
            self.embeddings.persist()

        if result.decision:
            await self.knowledge_graph.record_outcome(domain, result.decision.action, result.success)

        self.audit.record(
            "execution_complete",
            goal,
            result.to_dict(),
            domain=domain,
        )
        
        logger.info(f"Saved result: domain={domain}, success={result.success}")

    # ============ RETRIEVE OPERATIONS ============
    
    async def recall_similar(
        self, 
        goal: str, 
        domain: str, 
        limit: int = 5,
        time_window_days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar past experiences.
        
        Tries in order:
        1. Vector similarity (if FAISS available)
        2. Semantic recall (if enabled)
        3. Episodic keyword matching
        
        Args:
            goal: Current goal to find matches for
            domain: Domain to search within
            limit: Max results to return
            time_window_days: Only return results from last N days (None = all)
        
        Returns:
            List of similar past experiences with metadata
        """
        results = []
        
        # Try vector search first (most accurate if available)
        if self.embeddings and self.embeddings.enabled:
            logger.debug(f"Attempting vector similarity search for: {goal[:80]}")
            vector_results = self.embeddings.search(goal, limit=limit)
            if vector_results:
                results = vector_results
                logger.info(f"Found {len(results)} vector matches")
        
        # Fallback to semantic recall if available
        if not results and self.semantic:
            logger.debug(f"Attempting semantic recall for domain: {domain}")
            results = await self.semantic.recall_domain(domain)
            if results:
                logger.info(f"Found {len(results)} semantic matches")
        
        # Fallback to episodic keyword matching
        if not results:
            logger.debug(f"Attempting episodic keyword matching")
            results = self.episodic.recall_similar(goal, domain, limit)
            logger.info(f"Found {len(results)} episodic matches")
        
        # Filter by time window if specified
        if time_window_days and results:
            cutoff = datetime.now() - timedelta(days=time_window_days)
            results = [r for r in results if self._parse_timestamp(r.get("timestamp")) > cutoff]
            logger.debug(f"Filtered to {len(results)} results within {time_window_days} days")
        
        return results[:limit]

    async def get_domain_knowledge(self, domain: str) -> List[Dict[str, Any]]:
        """
        Retrieve all knowledge about a specific domain.
        
        Returns knowledge from:
        1. Semantic memory (general patterns)
        2. Knowledge graph (relationships)
        
        Args:
            domain: Domain to query
        
        Returns:
            List of domain knowledge items
        """
        knowledge = []
        
        # Get semantic knowledge
        if self.semantic:
            semantic_items = await self.semantic.recall_domain(domain)
            if semantic_items:
                knowledge.extend(semantic_items)
                logger.info(f"Found {len(semantic_items)} semantic items for domain: {domain}")
        
        # Get knowledge graph relationships
        graph_items = await self.knowledge_graph.query_domain(domain)
        if graph_items:
            knowledge.extend(graph_items)
            logger.info(f"Found {len(graph_items)} graph items for domain: {domain}")
        
        return knowledge

    # ============ KNOWLEDGE GRAPH QUERIES ============
    
    async def get_action_success_rate(self, domain: str, action: str) -> float:
        """Get success rate for a specific action in a domain."""
        return await self.knowledge_graph.get_success_rate(domain, action)
    
    async def get_best_actions_in_domain(self, domain: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Get top N actions by success rate in a domain."""
        return await self.knowledge_graph.get_top_actions(domain, top_k)
    
    async def query_relationships(self, entity: str, relationship_type: str = "related_to") -> List[str]:
        """Query knowledge graph for related entities."""
        return await self.knowledge_graph.query_relationships(entity, relationship_type)

    # ============ PREFERENCE OPERATIONS ============
    
    def get_practices_hints(self) -> List[str]:
        """Get best practices hints from preferences."""
        return self.preferences.get_practices_hints()
    
    def set_user_preference(self, key: str, value: Any) -> None:
        """Store a user preference."""
        self.preferences.set(key, value)
    
    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a user preference."""
        return self.preferences.get(key, default)
    
    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all stored preferences."""
        return self.preferences.get_all()

    # ============ LEARNING & IMPROVEMENT ============
    
    async def extract_learnings(self, execution_result: AgentResult) -> List[str]:
        """
        Extract key learnings from an execution.
        
        Identifies:
        - What worked well
        - What failed and why
        - Patterns for future reference
        """
        learnings = []
        
        if not execution_result.success:
            learnings.append(f"Failed task: {execution_result.output[:200]}")
        else:
            learnings.append(f"Successful approach: Used action {execution_result.decision.action}")
        
        if execution_result.metadata:
            if "error" in execution_result.metadata:
                learnings.append(f"Error to avoid: {execution_result.metadata['error']}")
            if "best_practices" in execution_result.metadata:
                learnings.extend(execution_result.metadata["best_practices"])
        
        logger.info(f"Extracted {len(learnings)} learnings from execution")
        return learnings

    # ============ STATS & DIAGNOSTICS ============
    
    async def stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        return {
            "episodic_count": self.episodic.count(),
            "semantic_enabled": self.semantic is not None,
            "faiss_enabled": bool(self.embeddings and self.embeddings.enabled),
            "faiss_documents": len(self.embeddings.documents) if self.embeddings else 0,
            "audit_chain_valid": self.audit.verify_chain(),
            "preferences_count": len(self.preferences.get_all()),
            "knowledge_graph_nodes": await self.knowledge_graph.node_count(),
        }
    
    def health_check(self) -> Dict[str, bool]:
        """Check if all memory systems are operational."""
        return {
            "episodic_memory": self.episodic is not None,
            "semantic_memory": self.semantic is not None and self.config.enable_semantic_memory,
            "knowledge_graph": self.knowledge_graph is not None,
            "embeddings": bool(self.embeddings and self.embeddings.enabled),
            "preferences": self.preferences is not None,
            "audit_trail": self.audit is not None,
        }

    # ============ HELPER METHODS ============
    
    @staticmethod
    def _parse_timestamp(ts: Optional[str]) -> datetime:
        """Parse ISO format timestamp string."""
        if not ts:
            return datetime.min
        try:
            return datetime.fromisoformat(ts)
        except:
            return datetime.min
