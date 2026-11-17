import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  linkWithPopup,
  sendSignInLinkToEmail,
  isSignInWithEmailLink,
  signInWithEmailLink,
  signOut,
  reauthenticateWithPopup,
  reauthenticateWithCredential,
  EmailAuthProvider,
  type User,
} from "firebase/auth";
import {
  initializeAppCheck,
  ReCaptchaEnterpriseProvider,
  getToken,
} from "firebase/app-check";
export type Value = any;
export const runtime: Value = await fetch("/runtime-config.json")
  .then((r) => (r.ok ? r.json() : {}))
  .catch(() => ({}));
const firebaseConfig = await fetch("/__/firebase/init.json")
  .then((r) => (r.ok ? r.json() : null))
  .catch(() => null);
const firebase = firebaseConfig ? initializeApp(firebaseConfig) : null;
export const auth = firebase ? getAuth(firebase) : null;
const appCheck =
  firebase && runtime.appCheckSiteKey
    ? initializeAppCheck(firebase, {
        provider: new ReCaptchaEnterpriseProvider(runtime.appCheckSiteKey),
        isTokenAutoRefreshEnabled: true,
      })
    : null;
export async function api(
  path: string,
  method = "GET",
  data?: Value,
  binary = false,
): Promise<Value> {
  const headers: Record<string, string> = {};
  if (auth?.currentUser)
    headers.Authorization = "Bearer " + (await auth.currentUser.getIdToken());
  if (appCheck)
    headers["X-Firebase-AppCheck"] = (await getToken(appCheck)).token;
  if (data && !binary) headers["Content-Type"] = "application/json";
  const response = await fetch("/api/v1" + path, {
    method,
    headers,
    body: data ? (binary ? data : JSON.stringify(data)) : undefined,
    redirect: "follow",
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw Object.assign(new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail),
    ), { status: response.status });
  }
  return response.json();
}
export async function download(path: string, filename: string) {
  const headers: Record<string, string> = {};
  if (auth?.currentUser)
    headers.Authorization = "Bearer " + (await auth.currentUser.getIdToken());
  // Request a URL as JSON to avoid sending an Authorization header to Cloud Storage.
  const response = await fetch("/api/v1" + path + "?redirect=false", {
    headers,
  });
  if (!response.ok) throw new Error("Download unavailable");
  const { url } = await response.json();
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noreferrer";
  link.click();
}
export async function google() {
  if (!auth) throw new Error("Authentication is not configured");
  if (auth.currentUser)
    await linkWithPopup(auth.currentUser, new GoogleAuthProvider());
  else await signInWithPopup(auth, new GoogleAuthProvider());
}
export async function emailLink(email: string) {
  if (!auth) throw new Error("Authentication is not configured");
  sessionStorage.setItem("loginEmail", email);
  await sendSignInLinkToEmail(auth, email, {
    url: location.origin + "/login",
    handleCodeInApp: true,
  });
}
export function needsEmail() {
  return !!auth && isSignInWithEmailLink(auth, location.href);
}
export async function finishEmail(email: string) {
  if (!auth) return;
  if (sessionStorage.getItem("account-reauth") && auth.currentUser) {
    if (auth.currentUser.email !== email) throw new Error("Use the email address of the account being deleted");
    await reauthenticateWithCredential(auth.currentUser, EmailAuthProvider.credentialWithLink(email, location.href));
    sessionStorage.removeItem("account-reauth");
  } else await signInWithEmailLink(auth, email, location.href);
  sessionStorage.removeItem("loginEmail");
  history.replaceState({}, "", sessionStorage.getItem("account-delete-pending") ? "/#account" : "/");
  window.dispatchEvent(new Event("account-reauthenticated"));
}
export async function logout() {
  if (auth) await signOut(auth);
}
export type { User };

export async function reauthenticateGoogle() {
  if (!auth?.currentUser) throw new Error("Sign in to continue");
  await reauthenticateWithPopup(auth.currentUser, new GoogleAuthProvider());
}
export async function emailReauthentication() {
  if (!auth?.currentUser?.email) throw new Error("Sign in to continue");
  sessionStorage.setItem("account-reauth", "true");
  await emailLink(auth.currentUser.email);
}
export async function deletionStatus(receipt: string) {
  const response = await fetch("/api/v1/account/deletion", {
    headers: { Authorization: "Deletion " + receipt },
  });
  if (!response.ok) throw Object.assign(new Error("Deletion status unavailable"), { status: response.status });
  return response.json();
}
