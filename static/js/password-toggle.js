document.querySelectorAll(".password-toggle").forEach((button) => {
  const passwordField = document.getElementById(button.dataset.passwordTarget);
  if (!passwordField) return;

  button.addEventListener("click", () => {
    const isHidden = passwordField.type === "password";
    passwordField.type = isHidden ? "text" : "password";
    button.textContent = isHidden ? "Hide" : "Show";
    button.setAttribute("aria-pressed", String(isHidden));
    button.setAttribute(
      "aria-label",
      `${isHidden ? "Hide" : "Show"} ${passwordField.id === "password" ? "password" : "password confirmation"}`,
    );
  });
});
