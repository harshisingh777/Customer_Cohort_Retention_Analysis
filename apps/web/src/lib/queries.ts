/**
 * API query objects per page, built from URL state. Server prefetch and client hooks both call
 * these, so the query keys match and the client hydrates without refetching.
 */
import { apiQuery, DIM_KEYS, type Query } from "./search-params";

export const COHORT_KEYS = [...DIM_KEYS, "granularity", "measure"] as const;

export function summaryQueries(f: Query) {
  return {
    dims: apiQuery(f, DIM_KEYS),
    cohorts: apiQuery({ ...f, granularity: "month", measure: "customers" }, COHORT_KEYS),
  };
}

export function cohortQuery(f: Query) {
  return apiQuery(f, COHORT_KEYS);
}

export function repeatQueries(f: Query) {
  return {
    dims: apiQuery(f, DIM_KEYS),
    firstProduct: apiQuery(f, [...DIM_KEYS, "level"]),
  };
}

export function segmentQuery(f: Query) {
  return apiQuery(f, DIM_KEYS);
}

export function customerQuery(f: Query) {
  return apiQuery({ ...f, limit: 200 }, [...DIM_KEYS, "segment", "state", "sort", "limit"]);
}

export function channelQuery(f: Query) {
  return apiQuery(f, ["from", "to"]);
}
