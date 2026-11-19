
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_go_sample/main.dart';

void main() {
  testWidgets('Counter increments smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const RuntimeProbeApp());

    expect(find.text('Counter: 0'), findsOneWidget);

    await tester.tap(find.text('Increment'));
    await tester.pump();

    expect(find.text('Counter: 1'), findsOneWidget);
  });

  testWidgets('Loads project asset', (WidgetTester tester) async {
    await tester.pumpWidget(const RuntimeProbeApp());

    await tester.tap(find.text('Load project asset'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'This text came from the separately built sample project\'s Flutter asset bundle.',
      ),
      findsOneWidget,
    );
  });
}
