---
name: phosphor-icons-exports
title: Phosphor Icons Export Names for React
description: |
  Common Phosphor Icons (@phosphor-icons/react) export names differ from other libraries
  like Lucide. This skill maps frequently-used icon concepts to their actual Phosphor names
  to avoid "export not found" build errors.
triggers:
  - Importing icons from @phosphor-icons/react
  - Build fails with "export X was not found in module"
  - Replacing lucide-react icons with Phosphor equivalents
---

## Common Mismaps

| Concept / Lucide name | Phosphor name     |
|-----------------------|-------------------|
| ExternalLink          | ArrowSquareOut    |
| AlertCircle           | WarningCircle     |
| AlertCircle (alt)     | Warning           |
| AlertTriangle         | Warning           |
| CheckCircle           | CheckCircle       |
| X                     | X                 |
| XCircle               | XCircle           |
| Download              | Download          |
| FileText              | FileText          |
| Spinner               | Spinner           |
| ArrowLeft             | ArrowLeft         |
| Plus                  | Plus              |
| UserPlus              | UserPlus          |
| Check                 | Check             |
| Search                | MagnifyingGlass   |
| Trash                 | Trash             |
| Edit / Pencil         | PencilSimple      |
| Eye                   | Eye               |
| EyeOff                | EyeSlash          |
| Calendar              | Calendar          |
| Clock                 | Clock             |
| Settings              | Gear              |
| Menu (hamburger)      | List              |
| Copy                  | Copy              |
| MoreVertical          | DotsThreeVertical |
| ChevronDown           | CaretDown         |
| ChevronRight          | CaretRight        |
| ChevronUp             | CaretUp           |
| CaretLineLeft         | CaretLineLeft     |
| CaretLineRight        | CaretLineRight    |
| Upload                | CloudArrowUp      |
| LogOut                | SignOut           |
| LogIn                 | SignIn            |
| User                  | User              |
| Users                 | Users             |
| Bell                  | Bell              |
| Moon                  | Moon              |
| Sun                   | Sun               |
| Stethoscope           | Stethoscope       |
| Hospital              | Hospital          |
| FileText (alt)        | Article           |
| BookOpen              | BookOpen          |
| Stack / Layers        | Stack             |
| SquaresFour           | SquaresFour       |

## Quick Check Command

If unsure whether an export exists, run inside the project:

```bash
ls node_modules/@phosphor-icons/react/dist/csr/ | grep -i '<partial_name>'
```

## Build Error Pattern

When Next.js + Turbopack fails with:

```
The export <Name> was not found in module [project]/node_modules/@phosphor-icons/react/dist/index.es.js
Did you mean to import <Suggestion>?
```

1. Use the table above to find the correct name.
2. If not listed, use the Quick Check Command to find the exact `.es.js` file.
3. Replace the import and rebuild.
