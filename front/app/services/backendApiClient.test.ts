import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { deleteAction, deleteBinding } from "./backendApiClient";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("deleteBinding", () => {
  it("sends the binding ID and accepts a 204 response", async () => {
    let requestUrl = "";
    let requestMethod = "";
    globalThis.fetch = async (input, init) => {
      requestUrl = String(input);
      requestMethod = init?.method ?? "";
      return new Response(null, { status: 204 });
    };

    await deleteBinding("binding/one");

    assert.equal(requestUrl, "http://localhost:8080/api/bindings/binding%2Fone");
    assert.equal(requestMethod, "DELETE");
  });
});

describe("deleteAction", () => {
  it("sends the encoded action ID and accepts a 204 response", async () => {
    let requestUrl = "";
    let requestMethod = "";
    globalThis.fetch = async (input, init) => {
      requestUrl = String(input);
      requestMethod = init?.method ?? "";
      return new Response(null, { status: 204 });
    };

    await deleteAction("action/one");

    assert.equal(requestUrl, "http://localhost:8080/api/actions/action%2Fone");
    assert.equal(requestMethod, "DELETE");
  });
});
