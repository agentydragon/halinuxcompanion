# Home Assistant developers docs
git clone --depth=1 https://github.com/home-assistant/developers.home-assistant

# FreeDesktop Notification spec
curl https://specifications.freedesktop.org/notification-spec/latest-single/ | \
    pandoc --from=html --to=markdown-fenced_divs-native_divs-raw_html-header_attributes-link_attributes-bracketed_spans-native_spans \
    --strip-comments \
    -o freedesktop_notification_spec.md

# Clean up remaining span markup and navigation cruft
sed -i 's/{[^}]*}//g' freedesktop_notification_spec.md
sed -i 's/\[\]\([^[]*\)//g' freedesktop_notification_spec.md
sed -i '/^\[Jump to content\]/d' freedesktop_notification_spec.md
sed -i '/^\[\!\[Freedesktop/,+1d' freedesktop_notification_spec.md
sed -i '/^Show Contents:/d' freedesktop_notification_spec.md
sed -i '/^\[Top\](#)/d' freedesktop_notification_spec.md
sed -i 's/\\$//g' freedesktop_notification_spec.md
# Remove duplicate table of contents entries
sed -i '/^\[\[\[.*\]\]\]$/d' freedesktop_notification_spec.md
# Clean up empty brackets
sed -i 's/\[\s*\]//g' freedesktop_notification_spec.md
# Remove extra whitespace lines
sed -i '/^[[:space:]]*$/N;/\n[[:space:]]*$/d' freedesktop_notification_spec.md
