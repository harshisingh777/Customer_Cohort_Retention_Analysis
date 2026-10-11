/** Typed map of GET routes → response bodies, from the generated OpenAPI types. */
import type { components } from "./schema";

export type Schemas = components["schemas"];

export type Routes = {
  "/v1/meta": Schemas["MetaData"];
  "/v1/metrics": Schemas["MetricsDoc"];
  "/v1/summary": Schemas["Envelope_Summary_"];
  "/v1/cohorts/retention": Schemas["Envelope_CohortTable_"];
  "/v1/cohorts/curves": Schemas["Envelope_Curves_"];
  "/v1/repeat/second-order": Schemas["Envelope_SecondOrder_"];
  "/v1/repeat/first-product": Schemas["Envelope_FirstProduct_"];
  "/v1/segments/rfm": Schemas["Envelope_Rfm_"];
  "/v1/customers": Schemas["Envelope_CustomerPage_"];
  "/v1/channels": Schemas["Envelope_Channels_"];
  "/v1/data-health": Schemas["DataHealth"];
  "/v1/settings": Schemas["SettingsOut"];
  "/v1/users": Schemas["UserOut"][];
};

export type Route = keyof Routes;
export type Meta = Schemas["MetaData"];
export type MetricDef = Schemas["MetricDef"];
export type Finding = Schemas["Finding"];
export type CohortRow = Schemas["CohortRow"];
export type CustomerRow = Schemas["CustomerRow"];
export type CustomerDetail = Schemas["CustomerDetail"];

/** RFC 9457 problem details; `detail` is written for people and shown verbatim. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public requestId: string | null = null,
    public type: string | null = null,
  ) {
    super(detail);
  }
}
