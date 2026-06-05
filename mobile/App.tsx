import React, { useRef, useState } from "react";
import {
  ActivityIndicator,
  SafeAreaView,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View
} from "react-native";
import { WebView } from "react-native-webview";
import type { WebView as WebViewType } from "react-native-webview";

declare const process: {
  env: {
    EXPO_PUBLIC_REVUE_API_URL?: string;
  };
};

const REVUE_URL = (process.env.EXPO_PUBLIC_REVUE_API_URL || "https://www.revue.social").replace(/\/$/, "");

export default function App() {
  const webViewRef = useRef<WebViewType>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" />
      <WebView
        ref={webViewRef}
        source={{ uri: REVUE_URL }}
        style={styles.webview}
        startInLoadingState
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        javaScriptEnabled
        domStorageEnabled
        pullToRefreshEnabled
        allowsBackForwardNavigationGestures
        setSupportMultipleWindows={false}
        onLoadStart={() => {
          setIsLoading(true);
          setHasError(false);
        }}
        onLoadEnd={() => setIsLoading(false)}
        onError={() => {
          setIsLoading(false);
          setHasError(true);
        }}
        renderLoading={() => (
          <View style={styles.loading}>
            <Text style={styles.logo}>Revue</Text>
            <ActivityIndicator color="#bd6d2d" style={styles.spinner} />
            <Text style={styles.loadingText}>Opening your live Revue app</Text>
          </View>
        )}
      />

      {isLoading ? (
        <View pointerEvents="none" style={styles.floatingLoader}>
          <ActivityIndicator color="#bd6d2d" />
        </View>
      ) : null}

      {hasError ? (
        <View style={styles.errorOverlay}>
          <View style={styles.errorCard}>
            <Text style={styles.logo}>Revue</Text>
            <Text style={styles.errorTitle}>Could not open Revue</Text>
            <Text style={styles.errorText}>
              This app loads the same live website and data as revue.social. Check your connection and try again.
            </Text>
            <TouchableOpacity activeOpacity={0.86} style={styles.primaryButton} onPress={() => webViewRef.current?.reload()}>
              <Text style={styles.primaryText}>Reload</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#f4eadf"
  },
  webview: {
    flex: 1,
    backgroundColor: "#f4eadf"
  },
  loading: {
    alignItems: "center",
    backgroundColor: "#f4eadf",
    bottom: 0,
    justifyContent: "center",
    left: 0,
    position: "absolute",
    right: 0,
    top: 0
  },
  logo: {
    color: "#161411",
    fontFamily: "Georgia",
    fontSize: 52,
    fontStyle: "italic"
  },
  spinner: {
    marginTop: 22
  },
  loadingText: {
    color: "#746b63",
    fontSize: 15,
    marginTop: 12
  },
  floatingLoader: {
    alignItems: "center",
    backgroundColor: "rgba(244, 234, 223, 0.88)",
    borderRadius: 999,
    height: 42,
    justifyContent: "center",
    position: "absolute",
    right: 18,
    top: 58,
    width: 42
  },
  errorOverlay: {
    alignItems: "center",
    backgroundColor: "rgba(244, 234, 223, 0.96)",
    bottom: 0,
    justifyContent: "center",
    left: 0,
    padding: 22,
    position: "absolute",
    right: 0,
    top: 0
  },
  errorCard: {
    alignItems: "center",
    backgroundColor: "#fffdfa",
    borderColor: "#e8d8c8",
    borderRadius: 28,
    borderWidth: 1,
    padding: 26,
    shadowColor: "#8a5b35",
    shadowOffset: { height: 18, width: 0 },
    shadowOpacity: 0.13,
    shadowRadius: 24
  },
  errorTitle: {
    color: "#161411",
    fontSize: 22,
    fontWeight: "800",
    marginTop: 18
  },
  errorText: {
    color: "#746b63",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 8,
    textAlign: "center"
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#bd6d2d",
    borderRadius: 999,
    marginTop: 18,
    paddingHorizontal: 28,
    paddingVertical: 13
  },
  primaryText: {
    color: "#fffaf4",
    fontSize: 16,
    fontWeight: "800"
  }
});
