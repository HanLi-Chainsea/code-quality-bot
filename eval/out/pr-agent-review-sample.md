## PR Reviewer Guide 🔍

Here are some key observations to aid the review process:

### ⏱️ Estimated effort to review: 2 🔵🔵⚪⚪⚪

### 🧪 No relevant tests

### 🔒 No security concerns identified

### ⚡ Recommended focus areas for review

#### 
**Possible Issue**

The `discount` function does not validate that the `pct` (percentage) parameter does not exceed 100, which could lead to negative prices. Additionally, the function uses floating-point arithmetic for monetary values, which can cause precision issues.



**Possible Issue**

The `fetchUser` function concatenates the `id` parameter directly into the URL without validation, which could lead to injection attacks if an attacker controls the `id` input.



