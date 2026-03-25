export interface PaperAuthor {
  name: string;
  author_id?: string;
  institution?: string;
  name_en?: string;
  name_zh?: string;
}

export interface PaperInfo {
  title: string;
  authors: (string | PaperAuthor)[];
  year: number;
  venue: string;
  total_citations: number;
  doi?: string;
}

export interface ComprehensiveEval {
  overall_impact_score: string | number;
  overall_summary: string;
  key_findings: string[];
  citation_quality_distribution: Record<string, string | number>;
  depth_distribution: Record<string, string | number>;
  sentiment_distribution: Record<string, string | number>;
  influence_areas?: string[];
  notable_citations?: string[];
}

export interface CitationLocation {
  section?: string;
  context?: string;
  purpose?: string;
}

export interface Evaluation {
  citing_title: string;
  citing_year: number;
  citation_type: string;
  citation_depth: string;
  citation_sentiment: string;
  quality_score: number;
  summary: string;
  detailed_analysis: string;
  citation_locations: (string | CitationLocation)[];
  content_type: string;
  publication_source: string;
  publication_source_type?: string;
  publication_domain?: string;
  paper_influence_score?: number;
  paper_influence_level?: string;
  scholar_citation_count?: number;
  scholar_link?: string;
  fulltext_available?: boolean;
  reference_verified?: boolean;
}

export interface ScholarProfile {
  name: string;
  institution?: string;
  country?: string;
  tier?: string;
  level?: string;
  level_label?: string;
  honors?: string[] | string;
  citing_paper?: string;
  h_index?: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'root' | 'citation' | 'author' | 'concept';
  size: number;
  color?: string;
  year?: number;
  score?: number | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface LabelValuePair {
  labels: string[];
  values: (number | null)[];
}

export interface CitationTypeEntry {
  type: string;
  count: number;
  description: string;
}

export interface CitationPositionEntry {
  position: string;
  count: number;
}

export interface CitationThemeEntry {
  theme: string;
  frequency: number;
}

export interface ImpactScoreEntry {
  label: string;
  score: number;
  color_class?: string;
}

export interface PredictionMetricEntry {
  label: string;
  value: string | number;
  note?: string;
}

export interface InsightCard {
  color: string;
  icon: string;
  title: string;
  body: string;
}

export interface AdvancedAnalytics {
  time_distribution?: LabelValuePair;
  yearly_distribution?: Record<string, number>;
  country_distribution?: Record<string, number>;
  country_distribution_all?: LabelValuePair;
  country_distribution_renowned?: LabelValuePair;
  country_distribution_top?: LabelValuePair;
  institution_distribution?: Record<string, number>;
  scholar_level_distribution?: LabelValuePair;
  scholar_tier_distribution?: Record<string, number>;
  citation_description_analysis?: {
    citation_types?: CitationTypeEntry[];
    citation_positions?: CitationPositionEntry[];
    citation_themes?: CitationThemeEntry[];
    sentiment_distribution?: Record<string, number>;
    key_findings?: string[];
    citation_depth?: Record<string, number>;
    comprehensive_summary?: string;
    usage_type_distribution?: Record<string, number>;
    position_distribution?: Record<string, number>;
    depth_distribution?: Record<string, number>;
  };
  influence_prediction?: {
    trend_data?: { labels: string[]; actual: (number | null)[]; forecast: (number | null)[] };
    prediction_metrics?: PredictionMetricEntry[];
    impact_scores?: ImpactScoreEntry[];
    prediction_commentary?: string;
  };
  impact_prediction?: {
    predicted_trend?: Record<string, number>;
    metrics?: Record<string, string | number>;
    dimension_scores?: Record<string, number>;
    prediction_commentary?: string;
  };
  data_insights?: string[];
  insight_cards?: InsightCard[];
  profile_summary?: string;
}

export interface ReportData {
  paper: PaperInfo;
  comprehensive_eval: ComprehensiveEval;
  evaluations: Evaluation[];
  advanced_analytics: AdvancedAnalytics;
  scholar_profiles: ScholarProfile[];
  graph_data: GraphData;
  generated_at?: string;
  task_id?: string;
}
