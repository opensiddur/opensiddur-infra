// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
const firebase = vi.hoisted(() => ({
  currentUser: { email: "reader@example.test" }, popup: vi.fn(), credential: vi.fn(),
  email: vi.fn(), signIn: vi.fn(), credentialWithLink: vi.fn(() => "email-credential"),
}));
vi.mock("firebase/app", () => ({ initializeApp: () => ({}) }));
vi.mock("firebase/auth", () => ({
  getAuth: () => firebase, GoogleAuthProvider: class {},
  reauthenticateWithPopup: firebase.popup, reauthenticateWithCredential: firebase.credential,
  EmailAuthProvider: { credentialWithLink: firebase.credentialWithLink },
  sendSignInLinkToEmail: firebase.email, signInWithEmailLink: firebase.signIn,
  signInWithPopup: vi.fn(), linkWithPopup: vi.fn(), signOut: vi.fn(), isSignInWithEmailLink: () => true,
}));
vi.mock("firebase/app-check", () => ({ initializeAppCheck: vi.fn(), ReCaptchaEnterpriseProvider: class {}, getToken: vi.fn() }));
vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
const { reauthenticateGoogle, emailReauthentication, finishEmail } = await import("./api");
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); window.history.replaceState({}, "", "/login?synthetic=link"); });
it("reauthenticates the current Google user without linking another identity", async () => {
  await reauthenticateGoogle();
  expect(firebase.popup).toHaveBeenCalledWith(firebase.currentUser, expect.anything());
});
it("returns email-link users to pending deletion and reauthenticates the existing account", async () => {
  sessionStorage.setItem("account-delete-pending", "true");
  await emailReauthentication();
  expect(firebase.email).toHaveBeenCalledWith(firebase, "reader@example.test", expect.objectContaining({ handleCodeInApp: true }));
  await finishEmail("reader@example.test");
  expect(firebase.credential).toHaveBeenCalledWith(firebase.currentUser, "email-credential");
  expect(firebase.signIn).not.toHaveBeenCalled();
  expect(sessionStorage.getItem("account-reauth")).toBeNull();
  expect(sessionStorage.getItem("account-delete-pending")).toBe("true");
  expect(location.hash).toBe("#account");
});
it("rejects an email link for a different account", async () => {
  sessionStorage.setItem("account-reauth", "true");
  await expect(finishEmail("other@example.test")).rejects.toThrow("Use the email address");
  expect(firebase.credential).not.toHaveBeenCalled();
  expect(firebase.signIn).not.toHaveBeenCalled();
});
