from ddgs import DDGS
import json

def test_search():
    print("Testing DuckDuckGo Search...")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text("Deepfake images flooding news", max_results=3))
            print(f"Found {len(results)} results:")
            print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    test_search()
