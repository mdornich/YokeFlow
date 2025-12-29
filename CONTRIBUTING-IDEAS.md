# Contributing Ideas to YokeFlow

Welcome to YokeFlow! We encourage community contributions and experimentation. This document outlines areas where you can contribute and experiment with the platform.

## Project Background

YokeFlow evolved from [Anthropic's Autonomous Coding demo](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding), transforming it into an API-first platform with a TypeScript/React UI, comprehensive logging, Docker sandbox support, and many additional features.

While we've made significant improvements, there are still exciting opportunities to enhance the platform further.

## Current Limitations & Opportunities

### Core Limitations
The following limitations from the original demo still present opportunities for improvement:

1. **Greenfield Projects Only** - Currently limited to creating new projects from scratch
2. **Web Application Focus** - Primarily designed to create UI-based web applications
3. **Universal Browser Verification** - Verifies every feature with browser automation, even when unnecessary

### Platform Compatibility
- Developed and tested primarily on macOS
- May require adjustments for Windows environments
- Docker support helps with cross-platform consistency

## Areas for Contribution

We encourage contributors to fork the repository and experiment with new ideas. Here are some areas where you can make an impact:

### 1. Integration & Connectivity
- **GitHub Integration** - Add support for automatic repository creation, PR management, and issue tracking
- **Task Manager Integration** - Connect with external task management systems (Jira, Linear, etc.)
- **Spec Writer Companion** - Create or integrate with an AI-powered specification writing tool

### 2. User Interface Improvements
The current UI prioritizes functionality over polish. See [UI-NOTES.md](UI-NOTES.md) for details on potential improvements:
- Enhanced visual design and UX
- Better progress visualization
- Real-time session monitoring improvements
- Mobile responsiveness

### 3. Intelligent Agent Behavior
- **Selective Browser Testing** - Limit browser verification to UI-related tasks only
- **Dynamic Model Selection** - Choose coding models based on task complexity
- **Context-Aware Testing** - Smarter test generation based on task type

### 4. Project Management Features
- **Epic/Task/Test Editing** - Allow manual editing before coding sessions begin
- **Final Project Review** - Add comprehensive comparison between created app and original specs
- **Mid-Project Adjustments** - Support for spec changes during development

### 5. Prompt Engineering
For those with less coding experience, you can contribute by:
- Experimenting with initialization prompts for better task generation
- Optimizing coding prompts for specific project types
- Testing various project specifications to identify best practices
- Documenting what types of specs work best

## Technical Documentation

Various features and architectural decisions are documented in the `docs/` folder to help you understand the codebase:
- Architecture overview
- Database schema
- API documentation
- Development workflow

## Getting Started

1. **Fork the Repository** - Create your own fork to experiment freely
2. **Create Feature Branches** - Use descriptive branch names for your experiments
3. **Document Your Changes** - Update relevant documentation as you go
4. **Share Your Findings** - Open issues or discussions about your discoveries

## Additional Resources

- **[TODO-FUTURE.md](TODO-FUTURE.md)** - Detailed suggestions for future enhancements
- **[docs/developer-guide.md](docs/developer-guide.md)** - Technical guide for developers
- **[UI-NOTES.md](UI-NOTES.md)** - Specific UI improvement opportunities

## Community Guidelines

- **Experiment Freely** - Don't be afraid to try bold ideas
- **Share Knowledge** - Document your learnings for others
- **Collaborate** - Discuss ideas in issues before major changes
- **Test Thoroughly** - Ensure your changes don't break existing functionality

## Questions or Ideas?

Open an issue to discuss your ideas or ask questions. We're excited to see what the community builds with YokeFlow!

---

*Remember: YokeFlow is about pushing the boundaries of autonomous development. Your contributions help shape the future of AI-assisted coding.*