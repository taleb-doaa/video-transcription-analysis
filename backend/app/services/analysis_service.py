import json
from typing import Any

import requests

from app.core.config import settings

OLLAMA_URL = settings.ollama_url
OLLAMA_MODEL = settings.ollama_model
CHUNK_SIZE = settings.analysis_chunk_size
OLLAMA_TIMEOUT = settings.ollama_timeout


def _call_ollama(prompt: str) -> dict[str, Any]:
    """
    Send a prompt to Ollama and return the parsed JSON response.
    """

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_predict": 350,
                "num_ctx": 2048,
            },
        },
        timeout=OLLAMA_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    raw_response = data.get("response", "")

    if not raw_response:
        raise ValueError(
            "Ollama returned an empty response."
        )

    try:
        return json.loads(raw_response)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON returned by Ollama: {raw_response}"
        ) from exc


def _build_transcript(
    segments: list[dict[str, Any]],
) -> str:
    """
    Convert transcript segments into a formatted text.
    """

    return "\n".join(
        f"[{segment['start']:.2f}s - {segment['end']:.2f}s] "
        f"{segment['text']}"
        for segment in segments
    )


def _analyze_chunk(
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyze one transcript chunk using Ollama.
    """

    transcript = _build_transcript(segments)

    prompt = f"""
Tu es un assistant spécialisé dans l'analyse de vidéos
et de podcasts.

Analyse la transcription suivante et retourne UNIQUEMENT
un objet JSON valide.

Le JSON doit respecter exactement cette structure :

{{
    "number_of_speakers": null,
    "summary": "Résumé synthétique du contenu.",
    "key_points": [
        "Point clé 1",
        "Point clé 2",
        "Point clé 3"
    ],
    "topics": [
        "Sujet 1",
        "Sujet 2",
        "Sujet 3"
    ]
}}

RÈGLES STRICTES :

1. number_of_speakers

- Donne le nombre d'intervenants uniquement s'il est
  clairement identifiable dans la transcription.
- Sinon retourne null.
- Ne déduis pas plusieurs intervenants à partir de
  changements de phrases ou de paragraphes.

2. summary

- Rédige un résumé de 1 à 3 phrases maximum.
- Conserve uniquement les idées principales du passage.
- Évite les détails secondaires.

3. key_points

- Retourne entre 2 et 4 points clés.
- Chaque point doit correspondre à une idée importante.
- Ne répète pas les mêmes informations.
- Ignore les salutations, remerciements et informations
  secondaires.

4. topics

- Retourne entre 1 et 3 thèmes.
- Utilise des expressions courtes.
- Regroupe les thèmes similaires.
- N'utilise pas de phrases complètes.

5. IMPORTANT

- N'invente aucune information.
- Ne répète pas inutilement la transcription.
- Ne retourne aucun texte en dehors du JSON.
- Réponds uniquement en français.

TRANSCRIPTION :

{transcript}
"""

    return _call_ollama(prompt)


def _synthesize_results(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generate a concise and coherent global synthesis
    from all chunk analyses.
    """

    if not results:
        raise ValueError(
            "No chunk analysis results available."
        )

    summaries: list[str] = []
    key_points: list[str] = []
    topics: list[str] = []

    for result in results:
        summary = result.get("summary")

        if isinstance(summary, str) and summary.strip():
            summaries.append(summary.strip())

        result_points = result.get("key_points", [])

        if isinstance(result_points, list):
            for point in result_points:
                if isinstance(point, str) and point.strip():
                    key_points.append(point.strip())

        result_topics = result.get("topics", [])

        if isinstance(result_topics, list):
            for topic in result_topics:
                if isinstance(topic, str) and topic.strip():
                    topics.append(topic.strip())

    # Remove exact duplicates while preserving order.
    summaries = list(dict.fromkeys(summaries))
    key_points = list(dict.fromkeys(key_points))
    topics = list(dict.fromkeys(topics))

    # Keep the synthesis input reasonably small.
    summaries = summaries[:12]
    key_points = key_points[:40]
    topics = topics[:30]

    synthesis_input = f"""
RÉSUMÉS DES DIFFÉRENTS PASSAGES :

{chr(10).join(
    f"- {summary}"
    for summary in summaries
)}

POINTS CLÉS :

{chr(10).join(
    f"- {point}"
    for point in key_points
)}

THÈMES IDENTIFIÉS :

{chr(10).join(
    f"- {topic}"
    for topic in topics
)}
"""

    prompt = f"""
Tu es un expert en analyse automatique de vidéos,
podcasts et transcriptions.

Tu dois produire une SYNTHÈSE GLOBALE d'une vidéo
à partir de plusieurs analyses partielles.

Les analyses peuvent contenir des répétitions.
Tu dois donc fusionner les informations similaires
et supprimer les doublons.

Retourne UNIQUEMENT un objet JSON valide.

Structure obligatoire :

{{
    "number_of_speakers": null,
    "summary": "Résumé global de la vidéo.",
    "key_points": [
        "Point clé 1",
        "Point clé 2",
        "Point clé 3",
        "Point clé 4",
        "Point clé 5"
    ],
    "topics": [
        "Thème principal 1",
        "Thème principal 2",
        "Thème principal 3",
        "Thème principal 4",
        "Thème principal 5"
    ]
}}

RÈGLES STRICTES :

1. SUMMARY

- Produis un résumé global cohérent.
- Entre 4 et 7 phrases maximum.
- Ne répète pas les mêmes idées.
- Regroupe les informations provenant de plusieurs passages.
- Conserve uniquement les idées réellement importantes.
- Ne mentionne pas "les chunks", "les segments" ou "les analyses".
- Le résumé doit être compréhensible indépendamment de la transcription.
- Réponds en français naturel et professionnel.

2. KEY POINTS

- Retourne EXACTEMENT entre 5 et 8 points.
- Chaque point doit représenter une idée réellement importante.
- Fusionne les points similaires.
- Supprime les doublons.
- N'inclus pas les salutations, remerciements ou appels à s'abonner.
- Utilise des formulations courtes et précises.

3. TOPICS

- Retourne entre 4 et 8 thèmes.
- Regroupe les thèmes similaires.
- Supprime les doublons et variantes synonymes.
- Utilise des groupes nominaux courts.
- Ne produis pas de phrases complètes.

4. NUMBER OF SPEAKERS

- Donne le nombre uniquement si les données permettent
  de l'identifier clairement.
- Sinon retourne null.
- Ne déduis jamais le nombre de speakers uniquement
  à partir du contenu textuel.

5. FIABILITÉ

- N'invente aucune information.
- Utilise uniquement les informations présentes
  dans les données fournies.
- Ne crée pas de faits supplémentaires.
- Ne répète pas inutilement les informations.

6. FORMAT

- JSON valide uniquement.
- Aucun Markdown.
- Aucun commentaire.
- Aucun texte avant ou après le JSON.

DONNÉES À SYNTHÉTISER :

{synthesis_input}
"""

    final_result = _call_ollama(prompt)

    return {
        "number_of_speakers": final_result.get(
            "number_of_speakers"
        ),
        "summary": final_result.get(
            "summary",
            "",
        ),
        "key_points": final_result.get(
            "key_points",
            [],
        ),
        "topics": final_result.get(
            "topics",
            [],
        ),
    }


def analyze_transcript(
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyze a complete transcript using Ollama.

    Large transcripts are split into chunks to avoid
    excessively large prompts and Ollama timeouts.

    Returns:
        {
            "number_of_speakers": int | None,
            "summary": str,
            "key_points": list[str],
            "topics": list[str],
        }
    """

    if not segments:
        raise ValueError(
            "Transcript is empty."
        )

    # ---------------------------------------------------------
    # SMALL TRANSCRIPT
    # ---------------------------------------------------------

    if len(segments) <= CHUNK_SIZE:

        result = _analyze_chunk(segments)

        return {
            "number_of_speakers": result.get(
                "number_of_speakers"
            ),
            "summary": result.get(
                "summary",
                "",
            ),
            "key_points": result.get(
                "key_points",
                [],
            ),
            "topics": result.get(
                "topics",
                [],
            ),
        }

    # ---------------------------------------------------------
    # LARGE TRANSCRIPT
    # ---------------------------------------------------------

    chunks = [
        segments[i:i + CHUNK_SIZE]
        for i in range(
            0,
            len(segments),
            CHUNK_SIZE,
        )
    ]

    print(
        f"Analyzing transcript: "
        f"{len(segments)} segments "
        f"in {len(chunks)} chunks."
    )

    results = []

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):
        print(
            f"Analyzing chunk "
            f"{index}/{len(chunks)} "
            f"({len(chunk)} segments)..."
        )

        result = _analyze_chunk(chunk)

        results.append(result)

    print("Generating final synthesis...")

    return _synthesize_results(results)