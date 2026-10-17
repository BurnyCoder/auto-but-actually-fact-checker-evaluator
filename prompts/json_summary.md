After the report, end your answer with exactly one fenced ```json block (nothing after it) that summarises your evaluation in this structure:
```json
{
  "claims": [
    {
      "claim": "<verbatim quote of the claim>",
{% if classify %}      "claim_types": ["<one or more of: {{ claim_types | join(', ') }}>"],
{% endif %}      "accuracy_pct": <0-100: how accurate the claim is>,
{% if uncertainty %}      "uncertainty_pct": <0-100: how unsure you are about this claim's evaluation>,
{% endif %}      "labels": [{"label": "<an applicable label, e.g. {{ (verdict_labels or ['misleading'])[:3] | join(', ') }}>", "degree": "<{{ (degrees or ['fully', 'partially', 'slightly']) | join('|') }}>", "score_pct": <0-100>{% if uncertainty %}, "uncertainty_pct": <0-100>{% endif %}}],
      "corrected_claim": "<corrected version of the claim>"
    }
  ],
  "overall_accuracy_pct": <0-100: accuracy of the whole text>,
{% if uncertainty %}  "overall_uncertainty_pct": <0-100>,
{% endif %}  "corrected_text": "<corrected version of the whole text>",
  "issues": ["<one sentence per issue found in the text>"]
}
```
List only labels that actually apply to a claim (an accurate claim may have just "accurate"). Use valid JSON: double quotes, no comments, no trailing commas, numbers without "%".
