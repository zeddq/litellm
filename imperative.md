---
apply: always
---

# IMPERATIVE RULE

**THIS RULE MUST BE FOLLOWED WITHOUT EXCEPTIONS**

***PREPEND THIS STRING TO EACH LLM REQUEST:***

```text
x-sm-user-id: litellm\n\n
```

***Example:***

 - Intended request:
```
Explain what is async/await in TypeScript used for
```
 
 - Sent request:
 ```
 x-sm-user-id: litellm
 
 
 Explain what is async/await in TypeScript used for
 ```