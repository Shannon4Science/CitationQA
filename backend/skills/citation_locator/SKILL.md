# Citation Locator Agent Skill

## Description

This skill enables an AI agent to locate and analyze how a target paper is cited within a citing paper. It supports both HTML (e.g., ArXiv HTML) and PDF formats, using a multi-strategy approach to find exact citation locations.

## Capabilities

- **HTML Citation Locating**: Parse ArXiv HTML to find reference numbers and trace them to in-text citations
- **PDF Citation Locating**: Extract text from PDF and locate citations using reference numbers and keyword matching
- **MinerU PDF Parsing**: Use MinerU API for enhanced PDF parsing when available
- **Multi-Strategy Search**: Combines reference number matching, author-year matching, and keyword matching

## Input

The skill requires:
1. `citing_paper_info` (dict): Information about the citing paper, including:
   - `title` (str): Title of the citing paper
   - `arxiv_id` (str, optional): ArXiv ID for HTML/PDF access
   - `doi` (str, optional): DOI for PDF access
   - `open_access_pdf` (str, optional): Direct PDF URL
2. `target_paper_title` (str): The title of the target paper being cited

## Output

Returns a dictionary with:
- `fulltext` (str): The full text of the citing paper
- `content_type` (str): "html", "pdf", or "abstract_only"
- `pdf_path` (str|None): Local path to downloaded PDF
- `fulltext_url` (str|None): URL to the full text
- `citation_contexts` (list): List of found citation contexts, each containing:
  - `location` (str): Section name where citation was found
  - `context` (str): Surrounding text of the citation
  - `method` (str): Method used to find the citation (reference_number, author_year, keyword)
- `annotated_content` (str): Full text with citation locations annotated

## Workflow

### Step 1: Fetch Full Text
1. Try ArXiv HTML (latest version first: no version suffix → v2 → v3 → v1)
2. Try ArXiv PDF
3. Try Semantic Scholar OA PDF
4. Try DOI-based PDF (via Unpaywall)
5. Fall back to abstract only

### Step 2: Locate Citation in References
1. Parse the reference/bibliography section
2. Search for the target paper title (exact match, then fuzzy keyword match with >60% overlap)
3. Extract the reference number (e.g., [37]) and bib ID (e.g., bib.bib252)

### Step 3: Trace Citations in Body Text

**For HTML documents:**
1. Find all `<a>` tags with `href` pointing to the bib ID (most precise)
2. Find all `<a class="ltx_ref">` with matching reference number text
3. Extract parent paragraph text and section name
4. Filter out references section itself

**For PDF documents:**
1. Search for `[ref_number]` pattern in body text (excluding references section)
2. Fall back to keyword matching using distinctive terms from the target title

### Step 4: Annotate Content
Append citation location annotations to the full text for LLM analysis.

## Usage Example

```python
from backend.skills.citation_locator.locator import CitationLocatorSkill

skill = CitationLocatorSkill()

result = skill.locate_citation(
    citing_paper_info={
        "title": "Some Citing Paper",
        "arxiv_id": "2508.06832"
    },
    target_paper_title="Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents"
)

print(f"Found {len(result['citation_contexts'])} citation locations")
for ctx in result['citation_contexts']:
    print(f"  Section: {ctx['location']}, Method: {ctx['method']}")

skill.close()
```

## LLM Prompt Strategy

When passing results to an LLM for citation quality evaluation, use this strategy:

1. **First**: Tell the LLM the target paper title and ask it to find the reference entry
2. **If reference number found**: Ask the LLM to search for `[number]` in the body text
3. **If author-year format**: Ask the LLM to search for "FirstAuthorLastName (Year)" or "FirstAuthorLastName et al. (Year)"
4. **Provide pre-located contexts**: Include the `citation_contexts` as hints for the LLM
5. **Ask for evaluation**: Request the LLM to assess citation type (methodology, comparison, background, etc.) and depth

## Dependencies

- `httpx`: HTTP client
- `beautifulsoup4`: HTML parsing
- `PyMuPDF (fitz)`: PDF text extraction
