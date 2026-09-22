import {describe, expect, it} from "vitest";

import {parseNetscapeCookies} from "./cookies.js";

describe("parseNetscapeCookies", () => {
  it("parses x.com session cookies and session-only rows", () => {
    const cookies = parseNetscapeCookies(
      [
        "# Netscape HTTP Cookie File",
        ".x.com\tTRUE\t/\tTRUE\t1815467431\tauth_token\tabc123",
        ".x.com\tTRUE\t/\tTRUE\t1818491431\tct0\tcsrf-value",
        "x.com\tFALSE\t/\tFALSE\t0\tlang\ten",
      ].join("\n"),
    );
    expect(cookies).toHaveLength(3);
    expect(cookies[0]).toMatchObject({
      name: "auth_token",
      value: "abc123",
      domain: ".x.com",
      secure: true,
      expires: 1815467431,
    });
    expect(cookies[2]).toMatchObject({name: "lang", expires: -1, secure: false});
  });
});
