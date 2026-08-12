"""Config-driven chip-tap chatbot layer.

The customer flow: they tap a business unit → issue type; that selection
carries a declared data-point contract + a pool of acknowledgment
templates. The pipeline enriches with exactly the data the issue type
asked for, picks a weighted-random template, and renders variables
against the enriched context.

Free-text is the fallback path; the intent library grows into a
training set for a distilled classifier over time.
"""
