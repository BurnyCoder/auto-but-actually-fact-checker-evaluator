After the report, end your answer with exactly one fenced ```json block (nothing after it) that summarises your evaluation in this structure:
```json
{
  "claims": [
    {
      "claim": "<verbatim quote of the claim>",
{% if classify %}      "claim_types": [{"type": "<one of: {{ claim_types | join(', ') }}>"{% if confidence %}, "confidence_pct": <0-100>{% endif %}}],
{% endif %}      "accuracy_pct": <0-100: how accurate the claim is>,
{% if confidence %}      "confidence_pct": <0-100: how confident you are in this claim's evaluation>,
{% endif %}{% if labels_on %}      "labels": [{"label": "<label>", "degree": "<{{ degrees | join('|') }}>", "score_pct": <0-100: how much the label applies>{% if confidence %}, "confidence_pct": <0-100>{% endif %}}],
{% endif %}{% if conditions %}      "assessments": [{"condition": "<condition name>", "finding": "<one-sentence result>", "score_pct": <0-100, meaning below>{% if confidence %}, "confidence_pct": <0-100>{% endif %}}],
{% endif %}      "corrected_claim": "<corrected version of the claim>"
    }
  ],
  "overall_accuracy_pct": <0-100: accuracy of the whole text>,
{% if confidence %}  "overall_confidence_pct": <0-100>,
{% endif %}  "corrected_text": "<corrected version of the whole text>",
  "issues": ["<one sentence per issue found in the text>"]
}
```
{% if labels_on %}
{% if score_all_labels %}
"labels" must contain one entry for EVERY one of these labels for EVERY claim (score_pct 0 and degree null when a label does not apply): {{ verdict_labels | join('; ') }}.
{% else %}
"labels" lists only the labels that actually apply to the claim, chosen from: {{ verdict_labels | join('; ') }}.
{% endif %}
{% endif %}
{% if conditions %}
"assessments" must contain one entry for EVERY one of these conditions for EVERY claim, with score_pct meaning:
{% for c in conditions %}
- {{ c.name }}: {{ c.score }}
{% endfor %}
{% endif %}
Use valid JSON: double quotes, no comments, no trailing commas, numbers without "%".
