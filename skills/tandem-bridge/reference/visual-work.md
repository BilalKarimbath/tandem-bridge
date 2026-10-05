# Visual work task template

Use this when asking a peer to build or review a visual artifact. Name the
artifact, target widths, and expected visual behavior. Ask the receiver to
render at every stated width, actually inspect the output, and return the
screenshot paths with any findings. Do not claim a render was inspected merely
because a build or screenshot command exited successfully.

```text
Artifact: <project-relative path>
Task: <specific visual change or review question>
Widths: <widths in pixels, e.g. 375 and 1440>
Done when: render at each width; inspect the images; report layout, clipping,
contrast and text issues; return screenshot paths and the files changed.
```

The sender should verify those screenshots before accepting the reply.
