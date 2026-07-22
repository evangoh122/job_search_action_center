export interface RubricDimension {
  key: string;
  label: string;
}

export const RUBRIC: RubricDimension[] = [
  { key: "structure", label: "Structure / STAR" },
  { key: "relevance", label: "Relevance to role" },
  { key: "specificity", label: "Specificity & evidence" },
  { key: "technical", label: "Technical depth" },
  { key: "communication", label: "Communication" },
];

export const FALLBACK_QUESTIONS: string[] = [
  "Tell me about a time you built or scaled a data platform from the ground up. What architecture decisions mattered most and why?",
  "Describe a situation where you had to resolve a major conflict with a senior stakeholder over data strategy or model output. How did you handle it?",
  "Walk me through your approach to evaluating and productionizing a machine-learning model. What rigor do you apply before release?",
  "Give an example of a responsible-AI or fairness tradeoff you navigated. What principles guided your decision?",
  "Tell me about a data or AI project that failed. What happened, what did you learn, and what would you do differently?",
  "How do you hire, mentor, and scale a high-performing data team? Share a concrete example.",
  "Describe a time you translated a complex technical insight into a business decision that moved a key metric.",
  "What is your vision for how AI should integrate with the business over the next 2–3 years, and what are the biggest risks?",
];

/**
 * Builds a prompt that asks the model to score a transcribed spoken interview answer.
 */
export function ratingPrompt(
  question: string,
  transcript: string,
  roleContext: string,
): string {
  return `You are a senior interviewer evaluating a candidate's spoken answer.

QUESTION: ${question}

ROLE CONTEXT: ${roleContext}

TRANSCRIPT: ${transcript}

Score the answer on these dimensions from 1 (poor) to 5 (excellent):
${RUBRIC.map((d) => `- ${d.key}: ${d.label}`).join("\n")}

Also provide an overall 1–5 score and two concrete, actionable improvements.

Reply with ONLY strict, minified JSON of exactly this shape and nothing else:

{"scores":{"structure":n,"relevance":n,"specificity":n,"technical":n,"communication":n},"overall":n,"feedback":"...","improvements":["...","..."]}

Do not include markdown fences, explanations, or prose.`;
}

/**
 * Builds a prompt that asks the model to generate tailored interview questions.
 */
export function questionsPrompt(roleTitles: string[]): string {
  return `You are an expert technical interviewer. Generate exactly 6 tailored interview questions (mix behavioral-STAR and technical/strategy) for a senior candidate targeting these roles: ${roleTitles.join(", ")}.

Reply with ONLY strict, minified JSON of exactly this shape and nothing else:

{"questions":["...","...","...","...","...","..."]}

Do not include markdown fences, explanations, or prose.`;
}
