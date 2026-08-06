"""
OMEGA Three-Mode Learning System
Handles proactive pattern matching, in-flight adaptations, and reactive post-mortems.
"""
import logging
from typing import Dict, Any, List
import time

logger = logging.getLogger(__name__)

class OmegaLearningEngine:
    def __init__(self, memory_store):
        """
        Expects a vector database or knowledge graph instance passed as memory_store.
        """
        self.memory = memory_store
        self.session_insights = []

    def proactive_learning(self, goal: str, context: Dict[str, Any]) -> List[str]:
        """
        Triggered before execution.
        Retrieves historical anti-patterns and successful strategies for similar goals.
        """
        logger.info(f"Initiating Proactive Learning for goal: {goal}")
        try:
            # Use semantic memory recall for pattern matching
            if hasattr(self.memory, 'recall'):
                past_insights = self.memory.recall(goal, limit=3)
                return past_insights if past_insights else []
            # Fallback to vector search if available
            elif hasattr(self.memory, 'search'):
                results = self.memory.search(goal, k=3)
                return [r.get('content', str(r)) for r in results] if results else []
            # Fallback to knowledge graph queries
            elif hasattr(self.memory, 'get_related'):
                related = self.memory.get_related(goal)
                return [f"Related to: {r['target']}" for r in related] if related else []
            else:
                logger.warning("Memory store does not support query methods")
                return []
        except Exception as e:
            logger.warning(f"Proactive learning retrieval failed: {e}")
            return []

    def in_flight_learning(self, task_id: str, error_msg: str, current_state: Dict) -> None:
        """
        Triggered during execution failures.
        Caches immediate blockers to prevent repeating the same mistake in the current session.
        """
        insight = f"Task {task_id} failed with error: {error_msg}. Avoid current approach."
        self.session_insights.append({
            "timestamp": time.time(),
            "type": "in_flight_correction",
            "insight": insight,
            "state": current_state
        })
        logger.info(f"Registered In-Flight Adaptation: {insight}")

    def reactive_learning(self, goal: str, execution_trace: List[Dict], success: bool) -> None:
        """
        Triggered after a goal completes (or fatally fails).
        Synthesizes the trace into long-term knowledge graph/vector rules.
        """
        logger.info("Initiating Reactive Post-Mortem Learning...")
        status = "SUCCESS" if success else "FAILURE"

        summary = f"Goal: {goal} | Status: {status} | Steps taken: {len(execution_trace)}"
        if not success:
            errors = [step.get('error') for step in execution_trace if step.get('error')]
            summary += f" | Critical Blockers: {', '.join(errors)}"

        try:
            # Store the synthesized learning in long-term memory
            # Try semantic memory store first
            if hasattr(self.memory, 'store'):
                self.memory.store(
                    key=f"post_mortem_{int(time.time())}",
                    value=summary,
                    domain="learning"
                )
                logger.info("Reactive learning successfully committed to semantic memory.")
            # Try knowledge graph node addition
            elif hasattr(self.memory, 'add_node'):
                import asyncio
                asyncio.create_task(self.memory.add_node(
                    name=summary[:100],
                    node_type="learning",
                    properties={"status": status, "goal": goal}
                ))
                logger.info("Reactive learning successfully committed to knowledge graph.")
            # Try embedding memory
            elif hasattr(self.memory, 'add_embeddings'):
                import asyncio
                asyncio.create_task(self.memory.add_embeddings(
                    texts=[summary],
                    metadatas=[{"type": "post_mortem", "success": success}]
                ))
                logger.info("Reactive learning successfully committed to embedding memory.")
            else:
                logger.warning("Memory store does not support storage methods, storing in session only")
                self.session_insights.append({
                    "timestamp": time.time(),
                    "type": "post_mortem",
                    "insight": summary,
                    "success": success
                })
        except Exception as e:
            logger.error(f"Failed to commit reactive learning: {e}")