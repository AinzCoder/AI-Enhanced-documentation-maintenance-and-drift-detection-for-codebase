import { describe, expect, it } from "vitest";
import { isValidGithubRepositoryUrl, MAX_ZIP_SIZE, validateZipFile } from "./repositoryImportValidation";

describe("GitHub repository URL validation", () => {
  it.each([
    "https://github.com/example/project",
    "https://github.com/example/project.git/",
    "HTTPS://GITHUB.COM/Example-Org/.github",
  ])("accepts %s", (url) => expect(isValidGithubRepositoryUrl(url)).toBe(true));

  it.each([
    "http://github.com/example/project", "git@github.com:example/project.git",
    "https://github.com.evil.example/example/project",
    "https://user:password@github.com/example/project",
    "https://github.com:443/example/project", "https://github.com/example/../project",
    "https://github.com/example/%2e%2e", "https://github.com/example/project?token=secret",
    "https://github.com/example/project#fragment", "https://github.com/example/project\n",
    "https://github.com/example--org/project", "https://github.com/example/.git",
    "https://github.com/example/project.",
  ])("rejects %s", (url) => expect(isValidGithubRepositoryUrl(url)).toBe(false));
});

it("validates the file extension and advisory size threshold", () => {
  expect(validateZipFile(new File(["x"], "repo.ZIP"))).toBeNull();
  expect(validateZipFile(new File(["x"], "repo.txt"))).toMatch(/extension/);
  expect(validateZipFile(new File([], "empty.zip"))).toMatch(/empty/);
  const large = new File(["x"], "large.zip");
  Object.defineProperty(large, "size", { value: MAX_ZIP_SIZE + 1, configurable: true });
  expect(validateZipFile(large)).toMatch(/25 MiB/);
  Object.defineProperty(large, "size", { value: MAX_ZIP_SIZE });
  expect(validateZipFile(large)).toBeNull();
});
