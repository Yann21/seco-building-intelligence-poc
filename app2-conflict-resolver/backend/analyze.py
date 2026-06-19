"""Run Claude conflict analysis over extracted documents and cache the result."""
import json
import os
from pathlib import Path
import anthropic
import json_repair
from extract import get_extracted

CACHE_PATH = Path(__file__).parent / "analysis.json"

SYSTEM_PROMPT = """Tu es un expert en réglementation de la construction et de la sécurité au travail au Luxembourg.
Tu analyses plusieurs documents réglementaires officiels pour identifier les conflits, lacunes et incohérences
qui peuvent affecter la conception d'un bâtiment ou d'un chantier.

Pour chaque conflit identifié, tu fournis:
1. Le sujet précis du conflit
2. Ce que dit chaque document (avec numéro d'article et valeur exacte)
3. La recommandation: quelle valeur appliquer (toujours la plus contraignante)
4. Le niveau de criticité (critique / majeur / mineur)
5. Le type de conflit (contradiction directe / lacune / ambiguïté terminologique)
"""

ANALYSIS_PROMPT = """Voici les textes de trois documents réglementaires luxembourgeois sur l'éclairage:

{doc_sections}

---

Analyse ces trois documents et identifie TOUS les conflits, contradictions, lacunes et ambiguïtés.
Concentre-toi particulièrement sur:
- Les valeurs numériques contradictoires (lux, durées, fréquences)
- Les ambiguïtés terminologiques qui peuvent mener à des erreurs de conception
- Les lacunes (un document couvre un cas que l'autre ignore)
- Les exigences qui ne sont pas les plus contraignantes selon les contextes

Réponds en JSON strict avec ce format:
{{
  "summary": "Résumé de l'analyse en 2-3 phrases",
  "conflicts": [
    {{
      "id": "C1",
      "title": "Titre court du conflit",
      "topic": "Catégorie: maintenance | illuminance | terminologie | autonomie | délai",
      "severity": "critique | majeur | mineur",
      "type": "contradiction | lacune | ambiguïté",
      "description": "Description claire du problème pour un architecte",
      "sources": [
        {{
          "doc_id": "ITM-CL-55.2",
          "article": "Art. X.Y",
          "quote": "Citation exacte du document",
          "value": "Valeur ou exigence spécifique"
        }}
      ],
      "recommendation": "Ce qu'il faut appliquer et pourquoi (principe de la valeur la plus contraignante)",
      "practical_impact": "Impact concret sur la conception ou la maintenance du bâtiment"
    }}
  ]
}}
"""


def run_analysis(docs: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    doc_sections = ""
    for doc_id, doc in docs.items():
        doc_sections += f"\n\n{'='*60}\n"
        doc_sections += f"DOCUMENT: {doc['title']}\n"
        doc_sections += f"Autorité: {doc['authority']} | Date: {doc['date']}\n"
        doc_sections += f"Périmètre: {doc['scope']}\n"
        doc_sections += f"{'='*60}\n\n"
        doc_sections += doc["full_text"]

    prompt = ANALYSIS_PROMPT.format(doc_sections=doc_sections)

    print("Running Claude analysis...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    # Extract JSON block from response
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    # Find the outermost JSON object
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]
    raw = raw.strip()

    result = json_repair.repair_json(raw, return_objects=True)
    result["documents"] = {
        doc_id: {k: v for k, v in doc.items() if k != "pages" and k != "full_text"}
        for doc_id, doc in docs.items()
    }
    return result


def get_analysis(force: bool = False) -> dict:
    if CACHE_PATH.exists() and not force:
        return json.loads(CACHE_PATH.read_text())

    docs = get_extracted()
    result = run_analysis(docs)
    CACHE_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("Analysis cached to analysis.json")
    return result


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    result = get_analysis(force=force)
    print(f"\nFound {len(result['conflicts'])} conflicts")
    for c in result["conflicts"]:
        print(f"  [{c['severity'].upper()}] {c['title']}")
