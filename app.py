from release_graph import graph


def main():
    result = graph.invoke(
        {
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
        }
    )

    print("\nRelease evidence:")
    print(result["release_evidence"])
    print("\nExplanation:", result["explanation"])
    print("\nLangGraph decision:", result["decision"])
    print("\nAction type:", result["action_type"])


if __name__ == "__main__":
    main()