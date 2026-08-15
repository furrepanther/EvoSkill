---
name: count-verification
description: Systematic counting verification for letters, characters, and words. Use when asked to count items in strings, words, or text - performs explicit enumeration with position numbers and cross-verification to prevent miscounting errors.
---

# Count Verification

## When to Use

Use this skill when asked to count:
- Letters in a word (e.g., "how many letters in 'committee'?")
- Characters in a string (including/excluding spaces)
- Words in a sentence or phrase

## Workflow

### Step 1: Enumerate Each Item with Position Number

List each item explicitly with its position:

```
For "committee":
1-c, 2-o, 3-m, 4-m, 5-i, 6-t, 7-t, 8-e, 9-e
```

### Step 2: Verify by Recounting from End

Count backward from the last item to confirm:

```
From end: 9-e, 8-e, 7-t, 6-t, 5-i, 4-m, 3-m, 2-o, 1-c = 9 ✓
```

### Step 3: Cross-Check

Sum the positions to confirm total:

```
1+2+3+4+5+6+7+8+9 = 45, divided by 9 positions = 9 items ✓
```

### Step 4: State Final Answer

```
"committee" has 9 letters.
```

## Examples

**Example 1: Letters in "banana"**
```
1-b, 2-a, 3-n, 4-a, 5-n, 6-a = 6 letters
From end: 6-a, 5-n, 4-a, 3-n, 2-a, 1-b = 6 ✓
"banana" has 6 letters.
```

**Example 2: Characters in "hello world" (with space)**
```
1-h, 2-e, 3-l, 4-l, 5-o, 6- , 7-w, 8-o, 9-r, 10-l, 11-d = 11
"hello world" has 11 characters (including space).
```

**Example 3: Words in "the quick brown fox"**
```
1-the, 2-quick, 3-brown, 4-fox = 4 words
"the quick brown fox" has 4 words.
```

## Common Errors to Avoid

- Stopping at first match without full enumeration
- Skipping repeated letters (e.g., "committee" has 2 m's and 2 e's)
- Not verifying with a second pass