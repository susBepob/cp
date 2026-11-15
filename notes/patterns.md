# Patterns

One entry per pattern, written in your own words after you've solved 2+ problems with it.
Format: when to recognize it → the core idea → a problem that shows it → the bug you made.

<!--
## Prefix sums
- Recognize: many range-sum queries on a static array.
- Idea: p[i] = a[0] + ... + a[i-1]; sum(l..r) = p[r+1] - p[l].
- Example: CSES 1646 Static Range Sum Queries
- My bug: forgot to use long long for p.
-->
