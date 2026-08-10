from release_graph import graph


def main():
    result = graph.invoke(
        {
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
            "review": {},
            "revision_count": 0,
            "review_status": "",
            "human_review_required": False,
        }
    )

    print("\nRelease evidence:")
    print(result["release_evidence"])
    print("\nExplanation:", result["explanation"])
    print("\nLangGraph decision:", result["decision"])
    print("\nAction type:", result["action_type"])
    print("\nReview:", result["review"])
    print("\nReview status:", result["review_status"])
    print("\nHuman review required:",result["human_review_required"]
)


if __name__ == "__main__":
    main()