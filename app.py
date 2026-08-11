from release_graph import graph


def main():
    """
    Run one ReleaseGuard assessment from the command line.

    This file is mainly useful for:
    - local testing
    - debugging
    - understanding the LangGraph flow without FastAPI or Streamlit

    The production-style user flow now goes through:
        Streamlit -> FastAPI -> LangGraph

    But app.py remains a simple way to execute the graph directly.
    """

    # -------------------------------------------------------------------
    # THREAD / CHECKPOINT IDENTIFIER
    # -------------------------------------------------------------------

    # Each checkpointed LangGraph execution needs a thread_id.
    #
    # LangGraph uses this ID to keep the saved state of one assessment
    # separate from another assessment.
    thread_id = thread_id

    # -------------------------------------------------------------------
    # RUN THE COMPLETE LANGGRAPH WORKFLOW
    # -------------------------------------------------------------------

    # graph.invoke() runs the workflow from start to finish and returns
    # the final merged LangGraph state.
    #
    # The graph itself will:
    # 1. fetch GitHub evidence
    # 2. evaluate deterministic release rules
    # 3. select the release path
    # 4. generate an AI explanation
    # 5. review/revise the explanation if needed
    # 6. finalize the review status
    result = graph.invoke(
        {
            # Initial/default graph state.
            # Each LangGraph node progressively fills or updates these fields.
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
            "review": {},
            "revision_count": 0,
            "review_status": "",
            "human_review_required": False,
            "human_decision": "",
        },

        # Because the graph was compiled with a checkpointer,
        # a thread_id must be supplied for every execution.
        config={
            "configurable": {
                "thread_id": thread_id
            }
        },
    )

    # -------------------------------------------------------------------
    # RETRIEVE THE SAVED CHECKPOINT
    # -------------------------------------------------------------------

    # graph.invoke() gives us the final result directly.
    #
    # graph.get_state() is different: it reads the latest state that was
    # saved by the LangGraph checkpointer for this thread_id.
    #
    # Comparing result and snapshot is useful for proving that
    # checkpointing is actually working.
    snapshot = graph.get_state(
        {
            "configurable": {
                "thread_id": thread_id
            }
        }
    )

    # -------------------------------------------------------------------
    # DISPLAY THE FINAL RESULT
    # -------------------------------------------------------------------

    # Raw engineering evidence collected from GitHub.
    print("\nRelease evidence:")
    print(result["release_evidence"])

    # Structured explanation produced by the LLM.
    print("\nExplanation:")
    print(result["explanation"])

    # Deterministic GO / GO WITH CONDITIONS / NO-GO decision.
    print("\nLangGraph decision:")
    print(result["decision"])

    # Operational action selected from the decision branch.
    print("\nAction type:")
    print(result["action_type"])

    # Structured response from the AI reviewer.
    print("\nReview:")
    print(result["review"])

    # Final review status after any review/revision cycle.
    print("\nReview status:")
    print(result["review_status"])

    # Indicates whether the automated workflow has escalated to a human.
    print("\nHuman review required:")
    print(result["human_review_required"])

    # Show the latest checkpoint saved for this assessment thread.
    print("\nSaved checkpoint state:")
    print(snapshot.values)


# -------------------------------------------------------------------
# SCRIPT ENTRY POINT
# -------------------------------------------------------------------

# This ensures main() runs only when this file is executed directly:
#
#     python app.py
#
# It will not automatically run if app.py is imported by another module.
if __name__ == "__main__":
    main()