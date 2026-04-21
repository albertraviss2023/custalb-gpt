from __future__ import annotations

from dataclasses import dataclass
from app.models.schemas import AddonDescriptor


@dataclass(slots=True)
class AddonSpec:
    id: str
    name: str
    tagline: str
    description: str
    category: str
    capabilities: list[str]
    system_prompt: str


CATALOG: dict[str, AddonSpec] = {
    "excel_data_analyst": AddonSpec(
        id="excel_data_analyst",
        name="Excel Data Analyst",
        tagline="Spreadsheet-first analysis and dashboarding",
        description="Cleans spreadsheet data, builds summaries, pivots, and formula-ready outputs.",
        category="analytics",
        capabilities=["xlsx profiling", "pivot strategy", "formula suggestions", "chart recommendations"],
        system_prompt=(
            "You are an expert Excel data analyst for enterprise work. "
            "Always provide spreadsheet-ready outputs with explicit worksheet plans, table structures, and formula-level details. "
            "When data analysis is requested, include: data cleaning steps, data validation rules, named ranges where useful, "
            "pivot table design (rows/columns/values/filters), and chart selection rationale. "
            "Use advanced formulas when appropriate (XLOOKUP, INDEX-MATCH, SUMIFS, COUNTIFS, IFERROR, LET, LAMBDA, dynamic arrays). "
            "For dashboards, propose a professional layout, color palette with accessible contrast, KPI cards, trend charts, and slicers. "
            "Recommend best visualization type based on the dataset shape and question (distribution, trend, comparison, composition, correlation). "
            "Keep outputs concise but implementation-ready, and call out assumptions."
        ),
    ),
    "unstructured_to_structured_transformer": AddonSpec(
        id="unstructured_to_structured_transformer",
        name="Unstructured to Structured",
        tagline="Converts raw text/images context into structured records",
        description=(
            "Transforms unstructured content into schema-aligned outputs compatible with Word, image metadata, and tabular exports."
        ),
        category="data-engineering",
        capabilities=["schema mapping", "field extraction", "normalization", "document-ready export hints"],
        system_prompt=(
            "You are a data structuring specialist. Convert unstructured inputs into clean schemas with explicit fields, "
            "types, and confidence notes."
        ),
    ),
    "professional_data_analyst": AddonSpec(
        id="professional_data_analyst",
        name="Professional Data Analyst",
        tagline="Multi-tool analysis across Python, R, SAS, and Stata",
        description="Designs rigorous analysis plans and code approaches for enterprise analytics workflows.",
        category="analytics",
        capabilities=["statistical design", "model diagnostics", "python/r/sas/stata workflow guidance", "report framing"],
        system_prompt=(
            "You are a senior professional data analyst across Python, R, SAS, and Stata. "
            "Choose the best language/workflow for the problem and explain why. "
            "Apply best-practice workflows for that language: reproducible projects, package choices, data validation, "
            "exploratory analysis, model diagnostics, statistical assumptions, sensitivity checks, and clear reporting. "
            "When coding is requested, provide clean, idiomatic snippets using common packages "
            "(Python: pandas/numpy/statsmodels/scikit-learn/matplotlib-seaborn; "
            "R: tidyverse/data.table/ggplot2/caret; "
            "SAS: PROC SQL/MEANS/REG/GLM; "
            "Stata: summarize/tabulate/regress/xtset workflows). "
            "Always include interpretation guidance and practical next-step recommendations."
        ),
    ),
    "data_lakehouse_builder": AddonSpec(
        id="data_lakehouse_builder",
        name="Data Lakehouse Builder",
        tagline="Designs lakehouse architectures and implementation plans",
        description="Helps users design medallion/lakehouse stacks, pipelines, governance, and deployment plans.",
        category="platform",
        capabilities=["architecture design", "storage zoning", "table formats", "pipeline and governance patterns"],
        system_prompt=(
            "You are a lakehouse architect. Produce implementation-ready architecture guidance with layers, technologies, "
            "data contracts, governance, and phased rollout plans."
        ),
    ),
    "latex_document_generator": AddonSpec(
        id="latex_document_generator",
        name="LaTeX Document Generator",
        tagline="Generates, structures, and compiles publication-quality LaTeX",
        description="Creates LaTeX source with sections, references, and compile guidance for polished documents.",
        category="documents",
        capabilities=["latex scaffolding", "academic and technical templates", "bibliography setup", "compile troubleshooting"],
        system_prompt=(
            "You are a LaTeX expert. Output clean, compilable LaTeX and concise explanation notes. Keep structure predictable "
            "and standards-compliant."
        ),
    ),
    "competency_interview_coach": AddonSpec(
        id="competency_interview_coach",
        name="Competency Interview Coach",
        tagline="Practice CBI panels with scoring and improvement plans",
        description=(
            "Runs competency-based interviews, simulates multi-member panels, scores competencies, and provides targeted coaching."
        ),
        category="career",
        capabilities=[
            "CBI panel simulation",
            "role-specific competencies",
            "scoring rubric",
            "feedback and improvement plan",
        ],
        system_prompt=(
            "You are an expert competency-based interview (CBI) coach. "
            "Run interviews using role-relevant competencies and STAR-style probing. "
            "When simulating a panel, clearly label each interviewer turn with a distinct panelist voice/persona "
            "(for example: Chair, Technical Lead, HR, Operations, Risk). "
            "After candidate answers, provide: "
            "(1) competency scores on a 1-5 scale, "
            "(2) evidence observed, "
            "(3) gaps, "
            "(4) concrete answer improvements, "
            "(5) follow-up question. "
            "For each session, include a role-fit verdict and a practical improvement checklist. "
            "Keep tone realistic, fair, and professional."
        ),
    ),
}


class AddonStore:
    def __init__(self) -> None:
        self._catalog = CATALOG

    def catalog(self) -> list[AddonSpec]:
        return list(self._catalog.values())

    def exists(self, addon_id: str) -> bool:
        return addon_id in self._catalog

    def get(self, addon_id: str) -> AddonSpec | None:
        return self._catalog.get(addon_id)

    def system_prompt_for(self, addon_id: str | None) -> str | None:
        if not addon_id:
            return None
        spec = self._catalog.get(addon_id)
        if not spec:
            return None
        return spec.system_prompt

    def as_descriptor(self, spec: AddonSpec, *, installed: bool) -> AddonDescriptor:
        return AddonDescriptor(
            id=spec.id,
            name=spec.name,
            tagline=spec.tagline,
            description=spec.description,
            category=spec.category,
            capabilities=spec.capabilities,
            installed=installed,
        )
