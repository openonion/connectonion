# Website Maintenance Guide

This guide explains how to add new features, pages, and content to the ConnectOnion documentation website.

## Overview

The documentation website follows a three-step process for adding new content:
1. Create a tutorial markdown file in `/docs-site/public/tutorials/`
2. Create a corresponding page component in `/docs-site/app/`
3. Update the sidebar navigation in `/docs-site/components/DocsSidebar.tsx`

## Step-by-Step Process

### 1. Create Tutorial Content

First, write your tutorial or documentation as a markdown file in the tutorials folder:

```bash
# Create your tutorial markdown file
touch docs-site/public/tutorials/your-new-feature.md
```

Example content structure:
```markdown
# Your Feature Title

Brief introduction to the feature.

## Overview
Explain what the feature does and why it's useful.

## Basic Usage
Show simple examples first.

## Advanced Usage
More complex examples and edge cases.

## API Reference
Detailed technical documentation.
```

### 2. Create the Page Component

Create a new page in the appropriate section of the app directory:

```bash
# For a new core concept
mkdir -p docs-site/app/your-feature
touch docs-site/app/your-feature/page.tsx
```

Basic page template:
```tsx
import { ArrowLeft, Copy, Check } from 'lucide-react'
import Link from 'next/link'
import { CopyButton } from '../../components/CopyButton'

export default function YourFeaturePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/" className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-8">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Home
      </Link>
      
      <h1 className="text-4xl font-bold mb-8">Your Feature Title</h1>
      
      {/* Your content here */}
    </div>
  )
}
```

### 3. Update Sidebar Navigation

Add your new page to the sidebar in `/docs-site/components/DocsSidebar.tsx`:

```typescript
const navigation: NavigationSection[] = [
  {
    title: 'Your Section',
    items: [
      // Add your new item
      { 
        title: 'Your Feature', 
        href: '/your-feature', 
        icon: YourIcon,
        keywords: ['keyword1', 'keyword2']
      },
    ]
  },
  // ... other sections
]
```

### 4. Update Search Mapping

Update the markdown-to-page mapping in `/docs-site/utils/markdownLoader.ts`:

```typescript
const MARKDOWN_TO_PAGE_MAP: Record<string, { href: string; section: string; title: string }> = {
  // Add your mapping
  'your-new-feature.md': { 
    href: '/your-feature', 
    section: 'Your Section', 
    title: 'Your Feature Title' 
  },
  // ... other mappings
}
```

## Content Guidelines

### Writing Principles

**Before writing any tutorial, read the [Writing & UI/UX Principles Guide](./writing-principles.md).**

Key principles:
- **Start Dead Simple** - First example should be minimal viable code
- **Progressive Disclosure** - Build complexity gradually
- **Show, Don't Tell** - Code examples before explanations
- **Every Code Block Must Run** - Test everything
- **One Concept Per Section** - Don't mix multiple ideas

### Tutorial Best Practices

1. **Start Simple**: Begin with the most basic use case
2. **Progressive Complexity**: Gradually introduce advanced features
3. **Code Examples**: Include runnable code snippets
4. **Visual Aids**: Use diagrams or flowcharts when helpful
5. **Real-World Scenarios**: Show practical applications

### Page Component Best Practices

1. **Consistent Layout**: Use the standard page template
2. **Interactive Elements**: Add copy buttons for code blocks
3. **Navigation**: Include "Back to Home" link
4. **Responsive Design**: Ensure mobile compatibility
5. **Accessibility**: Use semantic HTML and ARIA labels

### Search Optimization

1. **Keywords**: Add relevant keywords to navigation items
2. **Descriptive Titles**: Use clear, searchable titles
3. **Content Structure**: Use headers for better indexing
4. **Meta Information**: Include section and category info

## Common Page Patterns

### Code Example with Copy Button

```tsx
import { CommandBlock } from '../../components/CommandBlock'

<CommandBlock commands={['pip install connectonion']} />
```

### File Tree Display

```tsx
import { FileTree } from '../../components/FileTree'

<FileTree />
```

### Difficulty Badge

```tsx
import { DifficultyBadge } from '../../components/DifficultyBadge'

<DifficultyBadge difficulty="Beginner" />
```

## Testing Your Changes

1. **Start Development Server**:
   ```bash
   cd docs-site
   npm run dev
   ```

2. **Test Search**: Verify your content appears in search results

3. **Check Navigation**: Ensure sidebar links work correctly

4. **Mobile View**: Test responsive design

5. **Build Check**:
   ```bash
   npm run build
   ```

## Deployment Process

1. **Commit Your Changes**:
   ```bash
   git add .
   git commit -m "Add [feature] documentation"
   ```

2. **Push to Repository**:
   ```bash
   git push origin main
   ```

3. **Verify Deployment**: Check the live site after deployment

## Directory Structure

```
docs-site/
├── app/                    # Next.js pages
│   ├── your-feature/      # Your new feature page
│   │   └── page.tsx
│   └── ...
├── components/            # Reusable components
│   ├── DocsSidebar.tsx   # Main navigation
│   └── ...
├── public/
│   └── tutorials/        # Markdown documentation
│       ├── your-new-feature.md
│       └── ...
└── utils/
    ├── markdownLoader.ts # Search indexing
    └── ...
```

## Troubleshooting

### Search Not Finding Content
- Verify markdown file is in `/tutorials/`
- Check mapping in `markdownLoader.ts`
- Clear browser cache and reload

### Sidebar Link Not Working
- Confirm href matches page route
- Check for typos in navigation array
- Verify page component exports default function

### Build Errors
- Run `npm run build` locally first
- Check for missing imports
- Verify all TypeScript types

## Quick Checklist

When adding new content, ensure you:
- [ ] Created tutorial markdown in `/tutorials/`
- [ ] Created page component in `/app/`
- [ ] Added navigation item to sidebar
- [ ] Updated markdown-to-page mapping
- [ ] Added relevant keywords for search
- [ ] Tested search functionality
- [ ] Verified responsive design
- [ ] Ran build successfully

## Getting Help

- Check existing pages for examples
- Review component documentation
- Test changes locally before committing
- Keep commits focused and descriptive