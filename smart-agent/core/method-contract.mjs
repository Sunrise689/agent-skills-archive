const DECISIONS = new Set(["use", "combine", "fork", "skip"]);

const nonEmptyString = (value) => typeof value === "string" && value.trim().length > 0;
const nonEmptyStringArray = (value) => Array.isArray(value) && value.length > 0 && value.every(nonEmptyString);

export function extractSeedIds(catalog) {
  if (typeof catalog !== "string") return [];
  return [...catalog.matchAll(/^##\s+Seed\s+(?:\d+\s+·\s+)?([A-Z][A-Z0-9-]+)\s+·/gmi)].map((match) => match[1].toUpperCase());
}

export function validateMethodRefs(methodRefs, seedIds) {
  const allowed = new Set(seedIds.map((id) => String(id).toUpperCase()));
  const errors = [];
  if (!Array.isArray(methodRefs)) return ["method_refs must be an array"];
  for (const [index, ref] of methodRefs.entries()) {
    if (!ref || typeof ref !== "object" || Array.isArray(ref)) {
      errors.push(`method_refs[${index}] must be an object`);
      continue;
    }
    if (!nonEmptyString(ref.seed_id) || !allowed.has(ref.seed_id.toUpperCase())) errors.push(`method_refs[${index}].seed_id is not in the current catalog`);
    if (!nonEmptyString(ref.source)) errors.push(`method_refs[${index}].source is required`);
    if (!nonEmptyString(ref.source_version_or_commit)) errors.push(`method_refs[${index}].source_version_or_commit is required`);
    if (!DECISIONS.has(ref.decision)) errors.push(`method_refs[${index}].decision must be use/combine/fork/skip`);
    if (!nonEmptyStringArray(ref.signals)) errors.push(`method_refs[${index}].signals must be a non-empty string array`);
    if (!nonEmptyString(ref.reason) || ref.reason.trim().length < 10) errors.push(`method_refs[${index}].reason is too short`);
    if (!nonEmptyString(ref.change_summary)) errors.push(`method_refs[${index}].change_summary is required`);
  }
  return errors;
}

export function validateIntegrationRequests(requests, seedIds) {
  const allowed = new Set(seedIds.map((id) => String(id).toUpperCase()));
  const errors = [];
  if (!Array.isArray(requests)) return ["integration_requests must be an array"];
  for (const [index, request] of requests.entries()) {
    if (!request || typeof request !== "object" || Array.isArray(request)) {
      errors.push(`integration_requests[${index}] must be an object`);
      continue;
    }
    if (request.kind !== "method") errors.push(`integration_requests[${index}].kind must be method`);
    if (!nonEmptyString(request.seed_id) || !allowed.has(request.seed_id.toUpperCase())) errors.push(`integration_requests[${index}].seed_id is not in the current catalog`);
    if (!nonEmptyString(request.reason) || request.reason.trim().length < 10) errors.push(`integration_requests[${index}].reason is too short`);
  }
  return errors;
}

export function validateMethodComposition(composition, methodRefs, seedIds) {
  if (composition === undefined) return [];
  if (!Array.isArray(composition)) return ["method_composition must be an array"];
  const allowed = new Set(seedIds.map((id) => String(id).toUpperCase()));
  const referenced = new Set((Array.isArray(methodRefs) ? methodRefs : []).map((ref) => String(ref?.seed_id || "").toUpperCase()));
  const seen = new Set();
  const errors = [];
  for (const [index, item] of composition.entries()) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      errors.push(`method_composition[${index}] must be an object`);
      continue;
    }
    const seedId = String(item.seed_id || "").toUpperCase();
    if (!allowed.has(seedId)) errors.push(`method_composition[${index}].seed_id is not in the current catalog`);
    if (!referenced.has(seedId)) errors.push(`method_composition[${index}].seed_id must also appear in method_refs`);
    if (seen.has(seedId)) errors.push(`method_composition contains duplicate seed_id ${seedId}`);
    seen.add(seedId);
    if (!Number.isInteger(item.order) || item.order < 1) errors.push(`method_composition[${index}].order must be a positive integer`);
    if (!nonEmptyString(item.role)) errors.push(`method_composition[${index}].role is required`);
    if (item.depends_on !== undefined && (!Array.isArray(item.depends_on) || !item.depends_on.every((id) => allowed.has(String(id).toUpperCase()))) ) {
      errors.push(`method_composition[${index}].depends_on must contain current catalog IDs`);
    }
  }
  const orders = composition.map((item) => item?.order).filter((order) => Number.isInteger(order));
  if (new Set(orders).size !== orders.length) errors.push("method_composition orders must be unique");
  return errors;
}

export function methodContractErrors(design, seedIds) {
  return [
    ...validateMethodRefs(design?.method_refs, seedIds),
    ...validateIntegrationRequests(design?.integration_requests, seedIds),
    ...validateMethodComposition(design?.method_composition, design?.method_refs, seedIds),
  ];
}

export const METHOD_DECISIONS = [...DECISIONS];
