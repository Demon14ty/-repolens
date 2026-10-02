// Mirrors api/schemas.py. Keep the two files in sync.

export type AnalysisStatus = "complete" | "partial" | "unsupported";
export type Confidence = "High" | "Medium" | "Low" | "No reliable answer";

export interface SourcePreview {
  start_line: number;
  lines: string[];
  truncated: boolean;
}

export interface Citation {
  path: string;
  start_line: number;
  end_line: number;
  preview: SourcePreview | null;
}

export interface Repository {
  owner: string;
  name: string;
  full_name: string;
  description: string;
  stars: number;
  language: string;
  default_branch: string;
  html_url: string;
  license: string;
}

export interface Framework {
  name: string;
  confidence: string;
  evidence: string[];
  others: string[];
}

export interface ScoreFactor {
  label: string;
  points: number;
  max_points: number;
  reason: string;
}

export interface BeginnerScore {
  score: number;
  label: string;
  factors: ScoreFactor[];
}

export interface EntryPoint {
  path: string;
  reasons: string[];
  citations: Citation[];
  others: string[];
}

export interface LearningStep {
  number: number;
  path: string;
  category: string;
  why: string;
  difficulty_label: string;
  difficulty_score: number;
  minutes: number;
  relevant_code: string[];
  prerequisites: number[];
  citations: Citation[];
}

export interface FirstThirtyStep {
  number: number;
  path: string;
  category: string;
  minutes: number;
  difficulty_label: string;
  why: string;
  look_for: string;
  outcome: string;
  citations: Citation[];
}

export interface FirstThirtyPlan {
  steps: FirstThirtyStep[];
  total_minutes: number;
  outcomes: string[];
  is_limited: boolean;
  limited_notice: string | null;
}

export interface ConfusionItem {
  path: string;
  category: string;
  difficulty: number;
  importance: number;
  reasons: string[];
}

export interface ConfusionBucket {
  items: ConfusionItem[];
  total: number;
}

export interface ConfusionMap {
  start_here: ConfusionBucket;
  read_after_basics: ConfusionBucket;
  leave_for_later: ConfusionBucket;
}

export interface SkipItem {
  path: string;
  reason: string;
  file_count: number;
}

export interface ReadmeCheck {
  key: string;
  label: string;
  points: number;
  max_points: number;
  passed: boolean;
  evidence: string[];
  suggestion: string;
}

export interface ReadmeQuality {
  path: string | null;
  score: number;
  label: string;
  interpretation: string;
  notes: string[];
  checks: ReadmeCheck[];
}

export interface DependencyFile {
  path: string;
  packages: string[];
}

export interface Dependencies {
  packages: string[];
  files: DependencyFile[];
}

export interface FlowStep {
  label: string;
  path: string;
  detail: string;
}

export interface ContributionQuest {
  title: string;
  difficulty: string;
  minutes: number;
  problem: string;
  why_useful: string;
  likely_files: string[];
  concepts: string[];
  success_criteria: string[];
  hint: string;
  citations: Citation[];
}

export interface FilesSummary {
  tree_files: number;
  downloaded_files: number;
  analysed_python_files: number;
  python_files_in_tree: number;
  scored_files: number;
  by_category: Record<string, number>;
}

export interface Analysis {
  analysis_id: string;
  status: AnalysisStatus;
  summary: string;
  repository: Repository;
  framework: Framework;
  beginner_score: BeginnerScore | null;
  entry_point: EntryPoint | null;
  estimated_minutes: number;
  first_30_minutes: FirstThirtyPlan | null;
  learning_path: LearningStep[];
  confusion_map: ConfusionMap;
  skip_for_now: SkipItem[];
  readme_quality: ReadmeQuality | null;
  dependencies: Dependencies;
  code_flow: FlowStep[];
  contribution_quest: ContributionQuest | null;
  files_summary: FilesSummary;
  warnings: string[];
  limitations: string[];
  ai_explanations_available: boolean;
}

export interface QuestionAnswer {
  question: string;
  intent: string;
  answer: string;
  confidence: Confidence;
  citations: Citation[];
  limitations: string;
  unsupported: boolean;
}

export interface AIExplanation {
  available: boolean;
  message: string;
  overview: string;
  step_explanations: Record<string, string>;
  quest_text: Record<string, string>;
  warnings: string[];
}

export interface Health {
  status: "ok";
  version: string;
  ai_explanations_available: boolean;
}

export interface ApiErrorBody {
  code: string;
  title: string;
  message: string;
  details: Record<string, string | number> | null;
}
