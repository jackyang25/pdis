"""Every cap the Assistant enforces, in one place.

Schemas, readers, the loop and the API's request checks all read from here, so a
limit changes in one line and cannot disagree with its own schema. Each group says
what its numbers protect; tune them from the `assistant_question` usage log.
"""

# The loop. A typical question takes one to three tool steps; past six the agent is
# told to answer from what it has, so the step cap ends a search rather than failing it.
MAX_STEPS = 6
# Per model turn, reasoning included. A turn that reaches it fails the answer, so the
# cap is set well above the ~900 tokens the longest measured answers used.
MAX_OUTPUT_TOKENS = 8000

# Finding. 40 hits of about 360 characters is roughly 4k tokens: enough to choose
# what to read, and the overflow line says how many more matched.
MAX_FIND_HITS = 40
MAX_PRODUCT_DOC_HITS = 12
SNIPPET_BEFORE = 140
SNIPPET_AFTER = 220

# Reading. One read returns at most about 30k tokens; ranges page by 25 blocks and
# every truncation names how to get the rest.
MAX_RESULT_CHARS = 12_000
MAX_BLOCK_CHARS = 60_000
MAX_READ_CHARS = 120_000
MAX_PRODUCT_DOC_CHARS = 16_000
MAX_RANGE_BLOCKS = 25

# Visuals. Per call bounds one tool result; per question bounds what one answer can cost.
# At 1–1.5k tokens a slide, 16 keeps an image-heavy answer below what a text-only
# question cost before visuals were fetched on demand.
MAX_VISUALS_PER_CALL = 6
MAX_VISUALS_PER_QUESTION = 16
# Text block IDs named beside one viewed visual; a table-heavy slide can hold hundreds.
MAX_TEXT_BESIDE_VISUAL = 20

# Cited web sources. Only the first 20k characters are read, so the byte cap only
# stops a download that could never be used.
MAX_FETCH_CHARS = 20_000
MAX_FETCH_BYTES = 2_000_000
FETCH_TIMEOUT_SECONDS = 20

# The map, sent on every model call. These make its size follow how many results and
# documents are held, never how large they are; a workspace holds at most 20 results
# (five runs of four tools).
MAP_LINES_PER_RESULT = 40
MAP_HEADINGS_PER_DOCUMENT = 20
MAP_FIELD_VALUE_CHARS = 80

# What one request may carry. Generous: they stop abuse, not real workspaces.
MAX_REQUEST_MESSAGES = 200
MAX_REQUEST_BLOCKS = 50_000
MAX_REQUEST_IMAGES = 5_000
MAX_REQUEST_IMAGE_CHARS = 300_000_000
