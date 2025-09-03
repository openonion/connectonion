// Script to update all example pages with unified navigation
const fs = require('fs');
const path = require('path');

const examplePages = [
  { file: 'weather-bot', title: 'Weather Bot', index: 3 },
  { file: 'task-manager', title: 'Task Manager', index: 4 },
  { file: 'file-analyzer', title: 'File Analyzer', index: 5 },
  { file: 'api-client', title: 'API Client', index: 6 },
  { file: 'math-tutor-agent', title: 'Math Tutor Agent', index: 7 },
  { file: 'ecommerce-manager', title: 'E-commerce Manager', index: 8 }
];

function updateExamplePage(pageInfo) {
  const filePath = path.join(__dirname, '..', 'app', 'examples', pageInfo.file, 'page.tsx');
  
  if (!fs.existsSync(filePath)) {
    console.log(`File not found: ${filePath}`);
    return;
  }
  
  let content = fs.readFileSync(filePath, 'utf8');
  
  // Add navigation inconsistency comment if not present
  if (!content.includes('NAVIGATION INCONSISTENCY FOUND')) {
    content = `/*
  NAVIGATION INCONSISTENCY FOUND (2025-01-02):
  - Custom navigation with "Previous/Next in series" labels
  - No consistent breadcrumb navigation
  - Different from PageNavigation component
  - Being updated to use UnifiedNavigation
*/

${content}`;
  }
  
  // Update imports - add unified navigation
  if (!content.includes('UnifiedNavigation')) {
    // Remove Link import from react icons line if present
    content = content.replace(
      /import \{ ([^}]*)(ArrowRight|ArrowLeft)[^}]*\} from 'lucide-react'/,
      (match, p1) => {
        const icons = p1.split(',').map(i => i.trim())
          .filter(i => i && i !== 'ArrowRight' && i !== 'ArrowLeft');
        return `import { ${icons.join(', ')} } from 'lucide-react'`;
      }
    );
    
    // Add new imports after lucide-react
    content = content.replace(
      /from 'lucide-react'\n/,
      `from 'lucide-react'\nimport { UnifiedNavigation } from '../../../components/UnifiedNavigation'\nimport { getExampleNavigation } from '../../../utils/exampleNavigation'\n`
    );
    
    // Add CopyMarkdownButton if not present
    if (!content.includes('CopyMarkdownButton')) {
      content = content.replace(
        /import \{ UnifiedNavigation/,
        `import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'\nimport { UnifiedNavigation`
      );
    }
  }
  
  // Add navigation constant after function declaration
  if (!content.includes('getExampleNavigation')) {
    content = content.replace(
      /export default function [^(]+\(\) \{/,
      (match) => `${match}\n  const navigation = getExampleNavigation('/examples/${pageInfo.file}')`
    );
  }
  
  // Update responsive padding
  content = content.replace(
    /className="max-w-6xl mx-auto px-8 py-12/g,
    'className="max-w-6xl mx-auto px-4 md:px-8 py-8 md:py-12'
  );
  
  console.log(`Updated: ${pageInfo.file}/page.tsx`);
  fs.writeFileSync(filePath, content, 'utf8');
}

// Update all pages
examplePages.forEach(updateExamplePage);
console.log('All example pages updated!');