---
name: radix-slot-single-child-pitfall
description: >
  Radix UI's Slot component (used by `asChild` pattern) silently fails when
  it receives more than one child or an array of children. This commonly
  breaks navigation menus, buttons, and tooltips when trying to conditionally
  render labels/icons inside an `asChild` wrapper.
tags: [react, radix-ui, slot, aschild, nextjs, shadcn]
trigger: >
  You are using `asChild` on a Radix/Shadcn component and some children
  disappear, or the component stops rendering entirely, after adding
  conditional logic, `React.Children.map`, or fragments inside it.
---

## The Problem

Radix `Slot` uses `React.cloneElement` under the hood and expects exactly **one**
React element child. If you pass:

- An array (from `React.Children.map`)
- A fragment `<>`
- Multiple siblings
- A conditional that evaluates to `false` then `true` across renders

…the `Slot` silently fails and renders nothing.

## Common Broken Pattern

```tsx
// ❌ BAD — React.Children.map returns an array
function MenuButton({ children, asChild }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp>
      {React.Children.map(children, (child) => {
        if (someCondition && child.type === "span") return null;
        return child;
      })}
    </Comp>
  );
}
```

## The Fix

Keep the `asChild` component dumb — pass children through untouched.
Handle conditional rendering **in the parent** or **inside the single child**.

### Option A: Conditional in the parent (preferred)

```tsx
// ✅ GOOD — Slot receives exactly one <Link> element
function AppSidebar() {
  const { open } = useSidebar();
  return (
    <SidebarMenuButton asChild>
      <Link href="/">
        <HomeIcon />
        {open && <span>Home</span>}   {/* conditional lives here */}
      </Link>
    </SidebarMenuButton>
  );
}
```

### Option B: Extract a helper component

```tsx
function NavLink({ href, icon: Icon, label, open }) {
  return (
    <SidebarMenuButton asChild>
      <Link href={href} title={!open ? label : undefined}>
        <Icon />
        {open && <span>{label}</span>}
      </Link>
    </SidebarMenuButton>
  );
}
```

### Option C: Conditional inside the single child wrapper

```tsx
<SidebarMenuButton asChild>
  <button>
    <Icon />
    <span className={cn(open ? "inline" : "hidden")}>Label</span>
  </button>
</SidebarMenuButton>
```

## Pitfalls

- **Silent failure**: Slot doesn't throw an error; the element just vanishes.
- **Hidden by `asChild`**: The issue only manifests when `asChild={true}`; the
  fallback `button` path would work fine, making it hard to spot.
- **Fragment counts as multiple children**: Even `<><Icon /><span /></>` is two
  children from Slot's perspective.

## Verification

After fixing, check the React DevTools component tree:
1. The `Slot` should have exactly **one** child.
2. That child should be your element (`<a>`, `<button>`, `<Link>`).
3. Any conditional nodes should be nested **inside** that single child.