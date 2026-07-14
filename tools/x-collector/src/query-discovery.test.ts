import { describe, expect, it } from "vitest";

import {
  QueryChangedError,
  discoverOperations,
  discoverOperationsFromBundles,
} from "./query-discovery.js";

const MAIN_JS = `
  382445(e){e.exports={queryId:"account-query",operationName:"UserTweets",operationType:"query",
  metadata:{featureSwitches:["timeline_navigation_enabled","view_counts_enabled"],
  fieldToggles:["withArticlePlainText","withGrokAnalyze"]}}},
  100001(e){e.exports={queryId:"user-query",operationName:"UserByScreenName",operationType:"query",
  metadata:{featureSwitches:["profile_redirect_enabled"],fieldToggles:[]}}},
  100002(e){e.exports={queryId:"search-query",operationName:"SearchTimeline",operationType:"query",
  metadata:{featureSwitches:["search_timeline_enabled"],fieldToggles:["withArticlePlainText"]}}}
`;

describe("discoverOperations", () => {
  it("extracts query ids and declared switches", () => {
    const operations = discoverOperations(MAIN_JS, [
      "UserTweets",
      "UserByScreenName",
      "SearchTimeline",
    ]);

    expect(operations.UserTweets).toEqual({
      queryId: "account-query",
      protocol: "legacy",
      featureSwitches: ["timeline_navigation_enabled", "view_counts_enabled"],
      fieldToggles: ["withArticlePlainText", "withGrokAnalyze"],
    });
    expect(operations.UserByScreenName?.queryId).toBe("user-query");
    expect(operations.SearchTimeline?.queryId).toBe("search-query");
  });

  it("discovers Relay persisted queries across modular bundles", () => {
    const operations = discoverOperationsFromBundles(
      [
        "const unrelated = true",
        "params:{id:`relay-account-query`,metadata:{},name:`UserTweets`,operationKind:`query`,text:null}",
        "params:{id:`relay-user-query`,metadata:{},name:`UserByScreenName`,operationKind:`query`,text:null}",
      ],
      ["UserTweets", "UserByScreenName"],
    );

    expect(operations.UserTweets).toEqual({
      queryId: "relay-account-query",
      protocol: "relay",
      featureSwitches: [],
      fieldToggles: [],
    });
    expect(operations.UserByScreenName?.queryId).toBe("relay-user-query");
  });

  it("throws query_changed when an operation disappears", () => {
    expect(() => discoverOperations(MAIN_JS, ["MissingOperation"])).toThrowError(
      QueryChangedError,
    );
  });
});
