import logging
from typing import Dict, Any

from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger(__name__)


class ToolDebugLogger(CustomLogger):
    """
    Custom LiteLLM Logger to debug tool execution loops.

    It specifically watches for LLM responses that follow a "tool" role message.
    This helps pinpoint why an LLM might be failing to correct its tool usage
    after receiving an error.
    """

    def __init__(self):
        super().__init__()
        logger.info("🔧 ToolDebugLogger initialized")

    def log_success_event(
        self,
        kwargs: Dict[str, Any],
        response_obj: Any,
        start_time: float,
        end_time: float,
    ):
        """
        Called when a LiteLLM completion is successful.
        We check if the *previous* message was a tool output (especially an error).
        """
        try:
            messages = kwargs.get("messages", [])
            if not messages:
                return

            last_message = messages[-1]

            # Check if the context we just sent to the LLM ended with a tool result
            if last_message.get("role") == "tool":
                tool_content = last_message.get("content", "")
                tool_call_id = last_message.get("tool_call_id", "unknown")

                # Check if the tool result was an error
                is_error = "Error" in tool_content or "error" in tool_content

                log_level = logging.WARNING if is_error else logging.INFO

                logger.log(
                    log_level,
                    f"🔍 [ToolDebug] Round Analysis (ToolCallID: {tool_call_id})",
                )

                # 1. What we sent (The feedback/result)
                logger.log(
                    log_level,
                    f"   ➡️ Sent Context (Last Message):\n{tool_content[:500]}...",
                )

                # 2. What the LLM replied (The reaction)
                if (
                    response_obj
                    and hasattr(response_obj, "choices")
                    and response_obj.choices
                ):
                    reaction = response_obj.choices[0].message

                    # Did it try to call a tool again?
                    if hasattr(reaction, "tool_calls") and reaction.tool_calls:
                        for tc in reaction.tool_calls:
                            logger.log(
                                log_level,
                                f"   ⬅️ LLM Reaction (New Tool Call): {tc.function.name}({tc.function.arguments})",
                            )
                    else:
                        # Or did it give up/reply with text?
                        content = reaction.content or ""
                        logger.log(
                            log_level, f"   ⬅️ LLM Reaction (Text): {content[:200]}..."
                        )

        except Exception as e:
            logger.error(f"Error in ToolDebugLogger: {e}")

    async def async_log_success_event(
        self,
        kwargs: Dict[str, Any],
        response_obj: Any,
        start_time: float,
        end_time: float,
    ):
        """Async version of the success logger"""
        self.log_success_event(kwargs, response_obj, start_time, end_time)

    def log_failure_event(
        self,
        kwargs: Dict[str, Any],
        response_obj: Any,
        start_time: float,
        end_time: float,
    ):
        """Log failed LLM calls"""
        try:
            logger.error(f"❌ [ToolDebug] LLM Call Failed: {kwargs.get('model')}")
            if "messages" in kwargs:
                last_msg = kwargs["messages"][-1]
                logger.error(f"   Last Context: {last_msg}")
        except Exception:
            pass

    async def async_log_failure_event(
        self,
        kwargs: Dict[str, Any],
        response_obj: Any,
        start_time: float,
        end_time: float,
    ):
        """Async version of the failure logger"""
        self.log_failure_event(kwargs, response_obj, start_time, end_time)
